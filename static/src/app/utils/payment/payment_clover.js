/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/services/pos_store";

const { DateTime } = luxon;

export class PaymentClover extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.paymentLineResolvers = {};
        this.terminalStatus = 'disconnected';
    }

    /**
     * Send payment request to Clover terminal
     */
    sendPaymentRequest(uuid) {
        super.sendPaymentRequest(uuid);
        return this._cloverPay(uuid);
    }

    /**
     * Cancel ongoing payment
     */
    sendPaymentCancel(order, uuid) {
        super.sendPaymentCancel(order, uuid);
        return this._cloverCancel();
    }

    /**
     * Get pending payment line for Clover
     */
    pendingCloverLine() {
        return this.pos.getPendingPaymentLine("clover");
    }

    /**
     * Handle Odoo connection failure
     */
    _handleOdooConnectionFailure(data = {}) {
        const line = this.pendingCloverLine();
        if (line) {
            line.setPaymentStatus("retry");
        }
        this._showError(
            _t("Could not connect to the Odoo server. Please check your internet connection and try again.")
        );
        return Promise.reject(data);
    }

    /**
     * Call Clover API through Odoo backend proxy
     */
    _callClover(data, operation = 'sale') {
        return this.pos.data
            .silentCall("pos.payment.method", "proxy_clover_request", [
                [this.payment_method_id.id],
                data,
                operation,
            ])
            .catch(this._handleOdooConnectionFailure.bind(this));
    }

    /**
     * Build payment request data for Clover
     */
    _cloverPayData() {
        const order = this.pos.getOrder();
        const line = order.getSelectedPaymentline();
        const config = this.pos.config;

        return {
            amount: Math.round(line.amount * 100), // Convert to cents
            currency: this.pos.currency.name,
            externalPaymentId: `${order.uuid}--${order.session_id.id}`,
            orderId: order.name,
            note: `POS Order: ${order.name}`,
            autoAcceptPaymentConfirmations: true,
            autoAcceptSignature: true,
        };
    }

    /**
     * Initiate payment on Clover terminal
     */
    async _cloverPay(uuid) {
        const order = this.pos.getOrder();
        const line = order.payment_ids.find((paymentLine) => paymentLine.uuid === uuid);

        if (line.amount < 0) {
            this._showError(_t("Cannot process transactions with negative amount."));
            return Promise.resolve(false);
        }

        // Show welcome message on terminal
        await this._callClover({}, 'welcome');

        const data = this._cloverPayData();

        try {
            const response = await this._callClover(data, 'sale');
            return this._cloverHandleResponse(response, line);
        } catch (error) {
            this._showError(_t("Payment request failed: %s", error.message || error));
            line.setPaymentStatus("retry");
            return false;
        }
    }

    /**
     * Handle response from Clover API
     */
    _cloverHandleResponse(response, line) {
        if (!response) {
            this._showError(_t("No response received from Clover terminal."));
            line.setPaymentStatus("force_done");
            return false;
        }

        if (response.error) {
            const errorMsg = response.error.message || "Unknown error";
            if (response.error.status_code === 401) {
                this._showError(_t("Authentication failed. Please check your Clover credentials."));
            } else {
                this._showError(_t("Clover error: %s", errorMsg));
            }
            line.setPaymentStatus("force_done");
            return false;
        }

        // Check if payment was successful
        if (response.success || response.result === 'SUCCESS' || response.payment) {
            return this._handleSuccessResponse(response, line);
        }

        // Payment is pending - wait for confirmation
        if (response.status === 'PENDING' || response.result === 'PENDING') {
            line.setPaymentStatus("waitingCard");
            return this.waitForPaymentConfirmation(line);
        }

        // Payment declined or failed
        const message = response.message || response.reason || "Payment was not approved";
        this._showError(_t("Payment declined: %s", message));
        line.setPaymentStatus("retry");
        return false;
    }

    /**
     * Handle successful payment response
     */
    _handleSuccessResponse(response, line) {
        const payment = response.payment || response;

        // Set card details on payment line
        if (payment.cardTransaction) {
            const cardTx = payment.cardTransaction;
            line.card_type = cardTx.cardType || cardTx.type;
            line.transaction_id = cardTx.referenceId || payment.id;
            line.cardholder_name = cardTx.cardholderName || "";

            // Set receipt info if available
            if (cardTx.last4) {
                line.setReceiptInfo(`Card: ****${cardTx.last4}`);
            }
        }

        // Store Clover-specific fields
        line.clover_payment_id = payment.id;
        line.clover_order_id = payment.order?.id;
        line.clover_result = response.result || 'SUCCESS';
        line.clover_amount = payment.amount ? payment.amount / 100 : line.amount;
        line.clover_auth_code = payment.cardTransaction?.authCode;
        line.clover_card_type = payment.cardTransaction?.cardType;
        line.clover_card_last_four = payment.cardTransaction?.last4;

        // Show thank you message on terminal
        this._callClover({}, 'thank_you');

        return true;
    }

    /**
     * Wait for async payment confirmation from webhook
     */
    waitForPaymentConfirmation(line) {
        return new Promise((resolve) => {
            this.paymentLineResolvers[line.uuid] = resolve;
        });
    }

    /**
     * Handle Clover status response from webhook
     * This is called from pos_store.js when a websocket notification is received
     */
    async handleCloverStatusResponse() {
        const notification = await this.pos.data.silentCall(
            "pos.payment.method",
            "get_latest_clover_status",
            [[this.payment_method_id.id]]
        );

        if (!notification) {
            this._handleOdooConnectionFailure();
            return;
        }

        const line = this.pendingCloverLine();
        if (!line) {
            return;
        }

        const payment = notification.payment || notification;
        const isSuccess = payment.result === 'SUCCESS' || notification.success;

        if (isSuccess) {
            this._handleSuccessResponse(notification, line);
        } else {
            const message = payment.failureMessage || payment.reason || "Payment failed";
            this._showError(_t("Payment failed: %s", message));
        }

        // Resolve the waiting promise
        const resolver = this.paymentLineResolvers?.[line?.uuid];
        if (resolver) {
            resolver(isSuccess);
            delete this.paymentLineResolvers[line.uuid];
        } else {
            line?.handlePaymentResponse(isSuccess);
        }
    }

    /**
     * Cancel ongoing payment on Clover terminal
     */
    async _cloverCancel(ignoreError = false) {
        try {
            const response = await this._callClover({}, 'cancel');

            if (!ignoreError && response?.error) {
                this._showError(
                    _t("Cancelling the payment failed. Please cancel it manually on the Clover terminal.")
                );
            }
            return true;
        } catch (error) {
            if (!ignoreError) {
                this._showError(
                    _t("Cancelling the payment failed. Please cancel it manually on the Clover terminal.")
                );
            }
            return false;
        }
    }

    /**
     * Show error dialog
     */
    _showError(message, title = null) {
        this.env.services.dialog.add(AlertDialog, {
            title: title || _t("Clover Error"),
            body: message,
        });
    }

    /**
     * Close payment screen
     */
    close() {
        super.close();
        // Cancel any pending payment when leaving the payment screen
        this._cloverCancel(true);
    }
}

// Register the payment method
register_payment_method("clover", PaymentClover);
