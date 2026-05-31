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

