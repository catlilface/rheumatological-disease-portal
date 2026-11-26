// Package iam is the BFF's only production source of user identity.
package iam

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"os"
	"path/filepath"
	"time"

	"github.com/google/uuid"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/status"
	"portal/bff/internal/application"
	"portal/bff/internal/domain"
	common "portal/bff/internal/gen/commonv1"
	pb "portal/bff/internal/gen/iamv1"
)

type Client struct{ rpc pb.IamServiceClient }

func Dial(target, dir string) (*Client, error) {
	cert, err := tls.LoadX509KeyPair(filepath.Join(dir, "tls.crt"), filepath.Join(dir, "tls.key"))
	if err != nil {
		return nil, err
	}
	pem, err := os.ReadFile(filepath.Join(dir, "ca.crt"))
	if err != nil {
		return nil, err
	}
	ca := x509.NewCertPool()
	if !ca.AppendCertsFromPEM(pem) {
		return nil, errors.New("invalid IAM CA")
	}
	conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(credentials.NewTLS(&tls.Config{MinVersion: tls.VersionTLS12, RootCAs: ca, Certificates: []tls.Certificate{cert}})), grpc.WithDisableRetry())
	if err != nil {
		return nil, err
	}
	return &Client{pb.NewIamServiceClient(conn)}, nil
}

func unavailable() error { return domain.Fail(domain.Unavailable, "AUTHORIZATION_UNAVAILABLE") }
func failure(err error, unauthenticated string) error {
	switch status.Code(err) {
	case codes.Unauthenticated:
		return domain.Fail(domain.Unauthenticated, unauthenticated)
	case codes.AlreadyExists:
		return domain.Fail(domain.Conflict, "GUEST_SESSION_ALREADY_ISSUED")
	default:
		return unavailable()
	}
}
func login(p *pb.Principal) (*application.Login, error) {
	if p.GetActor().GetSubjectId() == "" || p.GetActor().GetSessionId() == "" || p.GetSessionExpiresAt().CheckValid() != nil {
		return nil, unavailable()
	}
	kind := "guest"
	roles := []string{}
	if !p.IsGuest {
		if len(p.Roles) != 1 {
			return nil, unavailable()
		}
		kind = "staff"
		switch p.Roles[0] {
		case pb.UserRole_USER_ROLE_ADMIN:
			roles = append(roles, "admin")
		case pb.UserRole_USER_ROLE_EDITOR:
			roles = append(roles, "editor")
		default:
			return nil, unavailable()
		}
	} else if len(p.Roles) != 0 {
		return nil, unavailable()
	}
	return &application.Login{Actor: &domain.Actor{ID: p.Actor.SubjectId, Kind: kind}, SessionID: p.Actor.SessionId, Roles: roles, Expires: p.SessionExpiresAt.AsTime()}, nil
}
func pair(t *pb.TokenPair, err error, code string) (*application.Login, error) {
	if err != nil {
		return nil, failure(err, code)
	}
	if t.GetAccessToken() == "" || t.GetRefreshToken() == "" || t.GetAccessExpiresAt().CheckValid() != nil || t.GetRefreshExpiresAt().CheckValid() != nil {
		return nil, unavailable()
	}
	l, err := login(t.Principal)
	if err != nil {
		return nil, err
	}
	l.Access, l.Refresh = t.AccessToken, t.RefreshToken
	l.AccessExpires = t.AccessExpiresAt.AsTime()
	return l, nil
}
func (c *Client) Guest(ctx context.Context, key, cookie string) (*application.Login, error) {
	p, e := c.rpc.CreateGuestSession(ctx, &pb.CreateGuestSessionRequest{RequestId: key, AccessToken: cookie})
	return pair(p, e, "SESSION_REQUIRED")
}
func (c *Client) SignIn(ctx context.Context, email, password string) (*application.Login, error) {
	p, e := c.rpc.SignInStaff(ctx, &pb.SignInStaffRequest{RequestId: uuid.NewString(), Email: email, Password: password})
	return pair(p, e, "INVALID_CREDENTIALS")
}
func (c *Client) Rotate(ctx context.Context, token, key string) (*application.Login, error) {
	p, e := c.rpc.RefreshTokens(ctx, &pb.RefreshTokensRequest{RequestId: key, RefreshToken: token})
	return pair(p, e, "SESSION_REQUIRED")
}
func (c *Client) Session(ctx context.Context, token string) (*application.Login, error) {
	if token == "" {
		return nil, domain.Fail(domain.Unauthenticated, "SESSION_REQUIRED")
	}
	p, e := c.rpc.Authenticate(ctx, &pb.AuthenticateRequest{RequestId: uuid.NewString(), AccessToken: token})
	if e != nil {
		return nil, failure(e, "SESSION_REQUIRED")
	}
	return login(p)
}
func (c *Client) Revoke(ctx context.Context, token string) error {
	_, e := c.rpc.EndSession(ctx, &pb.AuthenticateRequest{RequestId: uuid.NewString(), AccessToken: token})
	if e != nil {
		return failure(e, "SESSION_REQUIRED")
	}
	return nil
}
func (c *Client) Check(ctx context.Context, l *application.Login, action string, r domain.Resource, owner string) error {
	resource := &common.ResourceReference{ResourceType: r.Type, ResourceId: r.ID}
	if r.Version > 0 {
		version := uint64(r.Version)
		resource.Version = &version
	}
	d, e := c.rpc.CheckAccess(ctx, &pb.CheckAccessRequest{
		Context: &common.RequestContext{RequestId: uuid.NewString(), Actor: &common.ActorContext{SubjectId: l.Actor.ID, SessionId: l.SessionID}},
		Action:  action, Resource: resource, ResourceOwnerSubjectId: owner,
	})
	if status.Code(e) == codes.InvalidArgument {
		return domain.NotFound()
	}
	if e != nil {
		return failure(e, "SESSION_REQUIRED")
	}
	if !d.GetAllowed() {
		if d.GetReasonCode() == "ACCESS_REVOKED" {
			return domain.Fail(domain.Unauthenticated, "SESSION_REQUIRED")
		}
		return domain.NotFound()
	}
	if d.GetEvaluatedAt().CheckValid() != nil || d.GetExpiresAt().CheckValid() != nil ||
		d.ExpiresAt.AsTime().After(d.EvaluatedAt.AsTime().Add(5*time.Second)) || !time.Now().Before(d.ExpiresAt.AsTime()) {
		return unavailable()
	}
	return nil
}
