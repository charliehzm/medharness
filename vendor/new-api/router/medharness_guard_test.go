package router

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

func TestInstallMedHarnessResaleGuardBlocksResaleSurfaces(t *testing.T) {
	t.Setenv("MEDHARNESS_DISABLE_RESALE_SURFACE", "true")
	gin.SetMode(gin.TestMode)

	engine := gin.New()
	InstallMedHarnessResaleGuard(engine)
	engine.GET("/api/status", func(c *gin.Context) {
		c.Status(http.StatusOK)
	})

	blockedReq := httptest.NewRequest(http.MethodGet, "/api/user/register", nil)
	blockedResp := httptest.NewRecorder()
	engine.ServeHTTP(blockedResp, blockedReq)
	require.Equal(t, http.StatusNotFound, blockedResp.Code)
	require.Contains(t, blockedResp.Body.String(), "medharness_surface_disabled")

	allowedReq := httptest.NewRequest(http.MethodGet, "/api/status", nil)
	allowedResp := httptest.NewRecorder()
	engine.ServeHTTP(allowedResp, allowedReq)
	require.Equal(t, http.StatusOK, allowedResp.Code)
}

// TestInstallMedHarnessBypassGuardBlocksBypassSurfaces locks the ADR-18 §5
// disable list: every relay / control-plane surface that skips the §D.1 gate is
// 404'd, while the gated /v1 relay routes (where MedHarnessCompliance lives)
// stay reachable. Together with the middleware order/fail-closed tests this
// gives "every egress sub-route is gated-or-disabled" (relay 中间件命中率 100%).
func TestInstallMedHarnessBypassGuardBlocksBypassSurfaces(t *testing.T) {
	t.Setenv("MEDHARNESS_DISABLE_BYPASS_SURFACE", "true")
	gin.SetMode(gin.TestMode)

	engine := gin.New()
	InstallMedHarnessBypassGuard(engine)
	for _, p := range []string{"/v1/chat/completions", "/v1/messages", "/v1/embeddings", "/v1/audio/speech", "/v1/models"} {
		engine.POST(p, func(c *gin.Context) { c.Status(http.StatusOK) })
		engine.GET(p, func(c *gin.Context) { c.Status(http.StatusOK) })
	}

	blocked := []string{
		"/api/route", "/api/audit",
		"/mj/submit/imagine", "/fast/mj/submit/imagine", "/mj/image/123",
		"/suno/submit/music", "/pg/chat/completions",
		"/v1beta/models", "/v1beta/models/gemini-pro:generateContent",
		"/v1/video/generations", "/v1/videos", "/v1/videos/abc/remix", "/v1/videos/abc/content",
		"/kling/v1/videos/text2video", "/jimeng/",
	}
	for _, p := range blocked {
		req := httptest.NewRequest(http.MethodPost, p, nil)
		resp := httptest.NewRecorder()
		engine.ServeHTTP(resp, req)
		require.Equalf(t, http.StatusNotFound, resp.Code, "expected bypass surface %s to be 404", p)
		require.Containsf(t, resp.Body.String(), "medharness_surface_disabled", "expected disable reason for %s", p)
	}

	for _, p := range []string{"/v1/chat/completions", "/v1/messages", "/v1/embeddings", "/v1/audio/speech"} {
		req := httptest.NewRequest(http.MethodPost, p, nil)
		resp := httptest.NewRecorder()
		engine.ServeHTTP(resp, req)
		require.Equalf(t, http.StatusOK, resp.Code, "gated relay route %s must pass the bypass guard", p)
	}
	getReq := httptest.NewRequest(http.MethodGet, "/v1/models", nil)
	getResp := httptest.NewRecorder()
	engine.ServeHTTP(getResp, getReq)
	require.Equal(t, http.StatusOK, getResp.Code, "/v1/models listing must pass the bypass guard")
}

// TestInstallMedHarnessBypassGuardDisabled confirms the surface stays reachable
// when the operator opts out (env false), so the disable list is toggleable.
func TestInstallMedHarnessBypassGuardDisabled(t *testing.T) {
	t.Setenv("MEDHARNESS_DISABLE_BYPASS_SURFACE", "false")
	gin.SetMode(gin.TestMode)

	engine := gin.New()
	InstallMedHarnessBypassGuard(engine)
	engine.POST("/v1/video/generations", func(c *gin.Context) { c.Status(http.StatusOK) })

	req := httptest.NewRequest(http.MethodPost, "/v1/video/generations", nil)
	resp := httptest.NewRecorder()
	engine.ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)
}

