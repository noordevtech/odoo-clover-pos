/** @odoo-module */

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Custom Clover payment provider card component
 * This adds a Clover button alongside the other terminal options
 */
export class CloverPaymentProviderCard extends Component {
    static template = "Clover_pos.CloverPaymentProviderCard";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({
            isInstalled: true, // Module is already installed
        });
    }

    async selectClover() {
        // Set Clover as the selected payment terminal
        await this.props.record.update({
            payment_method_type: "terminal",
            use_payment_terminal: "clover",
            name: this.props.record.data.name || "Clover",
        });
    }
}

// Register the widget
export const CloverPaymentProviderCardParams = {
    component: CloverPaymentProviderCard,
};

registry.category("view_widgets").add("clover_payment_provider_card", CloverPaymentProviderCardParams);
