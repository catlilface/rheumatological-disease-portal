package httpapi

import (
	"net/http"
	"regexp"
	"time"

	"portal/bff/internal/application"
	"portal/bff/internal/domain"
)

type credentials struct {
	Email, Password string
	Consent         application.MedicalConsent `json:"medical_data_consent"`
}

var emailPattern = regexp.MustCompile(`^[^\s@]+@[^\s@]+\.[^\s@]+$`)

func (x credentials) Validate() error {
	if !emailPattern.MatchString(x.Email) {
		return invalid("body.email")
	}
	return nil
}
func principal(l *application.Login) any {
	return map[string]any{"kind": l.Actor.Kind, "roles": l.Roles, "session_expires_at": l.Expires}
}
func sessionCookies(c *call, l *application.Login) {
	for _, refresh := range []bool{false, true} {
		cookie := http.Cookie{Name: "portal_session", Path: "/", Secure: true, HttpOnly: true, SameSite: http.SameSiteLaxMode}
		if refresh {
			cookie.Name = "portal_refresh"
			cookie.Path = apiBase + "/auth/session"
			cookie.SameSite = http.SameSiteStrictMode
		}
		if l != nil {
			cookie.Expires = l.AccessExpires
			cookie.Value = l.Access
			if refresh {
				cookie.Expires = l.Expires
				cookie.Value = l.Refresh
			}
		} else {
			cookie.MaxAge = -1
			cookie.Expires = time.Unix(1, 0)
		}
		c.header.Add("Set-Cookie", cookie.String())
	}
}
func (c *call) issue(status int, l *application.Login, err error) (any, error) {
	if err != nil {
		return nil, err
	}
	c.status = status
	sessionCookies(c, l)
	return principal(l), nil
}
func (a *API) identity() {
	a.on("getMedicalDataPolicy", public, func(c *call) (any, error) {
		return map[string]string{"version": application.PolicyVersion, "text": "Демонстрационное согласие. Используйте только вымышленные данные.", "document_url": "/policy/personal-info-agreement.pdf"}, nil
	})
	a.on("createGuestSession", public, func(c *call) (any, error) {
		l, e := a.auth.Guest(c.ctx, c.id("Idempotency-Key"), c.accessCookie)
		return c.issue(201, l, e)
	})
	a.on("registerPatient", public, bind(func(c *call, x credentials) (any, error) {
		if a.demoRegister == nil {
			return nil, domain.NotFound()
		}
		l, e := a.demoRegister(c.id("Idempotency-Key"), x.Email, x.Password, x.Consent)
		return c.issue(201, l, e)
	}))
	a.on("signIn", public, bind(func(c *call, x credentials) (any, error) {
		l, e := a.auth.SignIn(c.ctx, x.Email, x.Password)
		return c.issue(200, l, e)
	}))
	a.on("getPrincipal", current, func(c *call) (any, error) { return principal(c.login), nil })
	a.on("refreshSession", public, func(c *call) (any, error) {
		l, e := a.auth.Rotate(c.ctx, c.refreshCookie, c.id("Idempotency-Key"))
		return c.issue(200, l, e)
	})
	a.on("signOut", current, func(c *call) (any, error) {
		if err := a.auth.Revoke(c.ctx, c.accessCookie); err != nil {
			return nil, err
		}
		sessionCookies(c, nil)
		c.status = 204
		return nil, nil
	})
	a.on("withdrawMedicalConsent", registered, func(c *call) (any, error) {
		c.status = 204
		return nil, c.actor.WithdrawConsent()
	})
	a.on("getOperation", current, func(c *call) (any, error) { return a.commands.Get(c.actor, c.id("owner"), c.id("operation_id")) })
}
