/** @odoo-module */

import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";

/**
 * Clover OAuth Connect Widget
 * Opens OAuth flow in popup and automatically handles token exchange
 */
export class CloverOAuthConnect extends Component {
    static template = "Clover_pos.CloverOAuthConnect";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            isConnecting: false,
            showSetupWizard: false,
            useManualMode: false,
        });
        this.oauthCheckInterval = null;

        // Listen for OAuth callback messages
        browser.addEventListener("message", this._onOAuthMessage.bind(this));
    }

    /**
     * Start OAuth connection flow
     */
    async connectToClover() {
        const authorizationUrl = this.props.record.data.clover_authorization_url;
        
        if (!authorizationUrl) {
            this.notification.add(_t("Please fill in Merchant ID and App ID first"), {
                type: "warning",
            });
            return;
        }

        this.state.isConnecting = true;

        // Open OAuth in popup
        const width = 600;
        const height = 700;
        const left = (window.screen.width - width) / 2;
        const top = (window.screen.height - height) / 2;

        this.oauthWindow = browser.open(
            authorizationUrl,
            "clover-oauth",
            `width=${width},height=${height},left=${left},top=${top},scrollbars=yes`
        );

        // Check if popup was blocked
        if (!this.oauthWindow || this.oauthWindow.closed) {
            this.notification.add(_t("Popup was blocked. Please allow popups for this site."), {
                type: "danger",
            });
            this.state.isConnecting = false;
            this.state.useManualMode = true;
            return;
        }

        // Set up timeout check (2 minutes)
        this.oauthCheckInterval = setInterval(() => {
            if (this.oauthWindow && this.oauthWindow.closed) {
                // User closed the popup manually
                clearInterval(this.oauthCheckInterval);
                this.state.isConnecting = false;
            }
        }, 1000);

        // Timeout after 2 minutes
        setTimeout(() => {
            if (this.state.isConnecting) {
                clearInterval(this.oauthCheckInterval);
                this.state.isConnecting = false;
                this.state.useManualMode = true;
                if (this.oauthWindow && !this.oauthWindow.closed) {
                    this.oauthWindow.close();
                }
                this.notification.add(
                    _t("OAuth timeout. Please check: 1) You are logged in to Clover, 2) The redirect URI is configured in your Clover App settings."),
                    { type: "warning", sticky: true }
                );
            }
        }, 120000);
    }

    /**
     * Handle OAuth callback message from popup
     */
    async _onOAuthMessage(event) {
        // Security check - only accept messages from expected origins
        const allowedOrigins = [
            window.location.origin,
            "https://sandbox.dev.clover.com",
            "https://www.clover.com",
        ];

        if (!allowedOrigins.includes(event.origin)) {
            return;
        }

        const data = event.data;
        
        if (data && data.type === "CLOVER_OAUTH_CALLBACK") {
            const { code, merchant_id } = data;
            
            if (code) {
                // Close popup if still open
                if (this.oauthWindow && !this.oauthWindow.closed) {
                    this.oauthWindow.close();
                }

                // Update the record with authorization code
                await this.props.record.update({
                    clover_authorization_code: code,
                });

                this.notification.add(_t("Authorization successful! Generating access token..."), {
                    type: "info",
                });

                // Automatically generate access token
                await this._generateAccessToken();
            }
        }
    }

    /**
     * Generate access token automatically
     */
    async _generateAccessToken() {
        try {
            const result = await this.orm.call(
                "pos.payment.method",
                "action_generate_access_token",
                [[this.props.record.resId]]
            );

            if (result && result.type === "ir.actions.client") {
                this.notification.add(_t("Access token generated successfully!"), {
                    type: "success",
                });
                
                // Refresh the record to show updated token
                await this.props.record.load();
            }
        } catch (error) {
            this.notification.add(
                _t("Failed to generate access token: %s", error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.isConnecting = false;
        }
    }

    /**
     * Check if connection is complete
     */
    get isConnected() {
        return !!this.props.record.data.clover_access_token;
    }

    /**
     * Check if we can connect (has required fields)
     */
    get canConnect() {
        return (
            this.props.record.data.clover_merchant_id &&
            this.props.record.data.clover_app_id &&
            this.props.record.data.clover_app_secret
        );
    }

    /**
     * Get connection status text
     */
    get connectionStatus() {
        if (this.isConnected) {
            return _t("Connected");
        } else if (this.props.record.data.clover_authorization_code) {
            return _t("Authorization pending");
        }
        return _t("Not connected");
    }

    /**
     * Open authorization page in new tab (manual mode)
     */
    openManualAuth() {
        const authorizationUrl = this.props.record.data.clover_authorization_url;
        if (authorizationUrl) {
            browser.open(authorizationUrl, "_blank");
        }
    }
}

// Register the widget
export const CloverOAuthConnectParams = {
    component: CloverOAuthConnect,
};

registry.category("view_widgets").add("clover_oauth_connect", CloverOAuthConnectParams);
