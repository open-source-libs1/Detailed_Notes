package com.capitalone.api.deposits.promotions.service;

import dev.openfeature.sdk.Client;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class FeatureFlagStartupPrinter implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(FeatureFlagStartupPrinter.class);
    private static final String FLAG_KEY = "aussiedor_targeted_incentive_eligibility_enabled";

    private final Client client;

    public FeatureFlagStartupPrinter(Client client) {
        this.client = client;
    }

    @Override
    public void run(String... args) {
        try {
            boolean flagValue = client.getBooleanValue(FLAG_KEY, false);
            log.info("Optimizely flag [{}] resolved to [{}]", FLAG_KEY, flagValue);
        } catch (Exception e) {
            log.error("Failed to evaluate Optimizely flag at startup", e);
        }
    }
}
