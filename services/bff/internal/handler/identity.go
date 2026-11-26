package handler

import (
	"net/http"
	"regexp"
	"time"

	"portal/bff/internal/models"
	"portal/bff/internal/service"
)

type credentials struct {
	Email, Password string
	Consent         service.MedicalConsent `json:"medical_data_consent"`
}

const (
	sessionCookieName = "portal_session"
	refreshCookieName = "portal_refresh"
	refreshCookiePath = apiBase + "/auth/session"
)

var emailPattern = regexp.MustCompile(`^[^\s@]+@[^\s@]+\.[^\s@]+$`)

func (x credentials) Validate() error {
	if !emailPattern.MatchString(x.Email) {
		return invalid("body.email")
	}
	return nil
}

func principal(l *service.Login) models.Principal {
	roles := map[string][]string{
		models.GuestActor:  {},
		models.StaffActor:  {"moderator"},
		models.MemberActor: {"patient"},
	}
	return models.Principal{Kind: l.Actor.Kind, Roles: roles[l.Actor.Kind], SessionExpiresAt: l.Expires}
}

func sessionCookies(c *call, l *service.Login) {
	for _, refresh := range []bool{false, true} {
		cookie := http.Cookie{Name: sessionCookieName, Path: "/", Secure: true, HttpOnly: true, SameSite: http.SameSiteLaxMode}
		if refresh {
			cookie.Name = refreshCookieName
			cookie.Path = refreshCookiePath
			cookie.SameSite = http.SameSiteStrictMode
		}
		if l != nil {
			cookie.Expires = l.Expires
			cookie.Value = l.Access
			if refresh {
				cookie.Value = l.Refresh
			}
		} else {
			cookie.MaxAge = -1
			cookie.Expires = time.Unix(1, 0)
		}
		c.header.Add("Set-Cookie", cookie.String())
	}
}

func (c *call) issue(status int, l *service.Login, err error) (any, error) {
	if err != nil {
		return nil, err
	}
	c.status = status
	sessionCookies(c, l)
	return principal(l), nil
}

func (a *API) identity() {
	a.on(opGetMedicalDataPolicy, public, func(c *call) (any, error) {
		return map[string]string{
			"version":      service.PolicyVersion,
			"text":         "Демонстрационное согласие. Используйте только вымышленные данные.",
			"document_url": "/policy/personal-info-agreement.pdf",
		}, nil
	})
	a.on(opCreateGuestSession, public, func(c *call) (any, error) {
		l, e := a.auth.Guest(c.id(idempotencyHeader), c.accessCookie)
		return c.issue(http.StatusCreated, l, e)
	})
	a.on(opRegisterPatient, public, bind(func(c *call, x credentials) (any, error) {
		l, e := a.auth.Register(c.id(idempotencyHeader), x.Email, x.Password, x.Consent)
		return c.issue(http.StatusCreated, l, e)
	}))
	a.on(opSignIn, public, bind(func(c *call, x credentials) (any, error) {
		l, e := a.auth.SignIn(x.Email, x.Password)
		return c.issue(http.StatusOK, l, e)
	}))
	a.on(opGetPrincipal, current, func(c *call) (any, error) { return principal(c.login), nil })
	a.on(opRefreshSession, public, func(c *call) (any, error) {
		l, e := a.auth.Rotate(c.refreshCookie, c.id(idempotencyHeader))
		return c.issue(http.StatusOK, l, e)
	})
	a.on(opSignOut, current, func(c *call) (any, error) {
		a.auth.Revoke(c.login)
		sessionCookies(c, nil)
		c.status = http.StatusNoContent
		return nil, nil
	})
	a.on(opWithdrawMedicalConsent, registered, func(c *call) (any, error) {
		c.status = http.StatusNoContent
		return nil, c.actor.WithdrawConsent()
	})
	a.on(opGetOperation, current, func(c *call) (any, error) { return a.commands.Get(c.actor, c.id("owner"), c.id("operation_id")) })
}
