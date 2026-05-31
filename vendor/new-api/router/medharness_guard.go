package router

import (
	"net/http"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/gin-gonic/gin"
)

var medHarnessBlockedPrefixes = []string{
	"/api/oauth",
	"/api/user/oauth",
	"/api/user/topup",
	"/api/subscription",
	"/api/redemption",
	"/api/stripe",
	"/api/creem",
	"/api/waffo",
	"/api/custom-oauth-provider",
	"/api/option/waffo-pancake",
	"/dashboard/billing",
	"/v1/dashboard/billing",
	"/console/topup",
	"/wallet",
	"/subscriptions",
	"/redemption-codes",
	"/oauth",
	"/sign-up",
	"/register",
}

var medHarnessBlockedExact = map[string]struct{}{
	"/api/user/register":                 {},
	"/api/user/aff":                      {},
	"/api/user/aff_transfer":             {},
	"/api/user/pay":                      {},
	"/api/user/amount":                   {},
	"/api/user/stripe/pay":               {},
	"/api/user/stripe/amount":            {},
	"/api/user/creem/pay":                {},
	"/api/user/waffo/pay":                {},
	"/api/user/waffo/amount":             {},
	"/api/user/waffo-pancake/pay":        {},
	"/api/user/waffo-pancake/amount":     {},
	"/api/option/payment_compliance":     {},
	"/api/user/epay/notify":              {},
	"/api/subscription/epay/notify":      {},
	"/api/subscription/epay/return":      {},
}

// InstallMedHarnessResaleGuard makes upstream resale/self-service surfaces
// unreachable in MedHarness deployments while keeping the subtree rebaseable.
func InstallMedHarnessResaleGuard(engine *gin.Engine) {
	if !common.GetEnvOrDefaultBool("MEDHARNESS_DISABLE_RESALE_SURFACE", true) {
		return
	}

	engine.Use(func(c *gin.Context) {
		path := normalizeMedHarnessPath(c.Request.URL.Path)
		if medHarnessPathBlocked(path) {
			c.AbortWithStatusJSON(http.StatusNotFound, gin.H{
				"error": gin.H{
					"code": "medharness_surface_disabled",
					"msg":  "endpoint disabled",
				},
			})
			return
		}
		c.Next()
	})
}

func normalizeMedHarnessPath(path string) string {
	normalized := strings.ToLower(path)
	if normalized != "/" {
		normalized = strings.TrimRight(normalized, "/")
	}
	if normalized == "" {
		return "/"
	}
	return normalized
}

func medHarnessPathBlocked(path string) bool {
	if _, ok := medHarnessBlockedExact[path]; ok {
		return true
	}
	for _, prefix := range medHarnessBlockedPrefixes {
		if path == prefix || strings.HasPrefix(path, prefix+"/") {
			return true
		}
	}
	return false
}
