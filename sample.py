src/main/java/com/capitalone/api/deposits/promotions/configuration/OptimizelyOpenFeatureConfiguration.java


package com.capitalone.api.deposits.promotions.configuration;

import dev.openfeature.sdk.Client;
import dev.openfeature.sdk.OpenFeatureAPI;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// Use the same Optimizely/provider imports that exist in your sample repo.
// Let IntelliJ auto-import them after dependencies are added.

@Configuration
public class OptimizelyOpenFeatureConfiguration {

    private static final Logger log = LoggerFactory.getLogger(OptimizelyOpenFeatureConfiguration.class);

    @Bean
    public Client openFeatureClient() throws Exception {
        String clientId = System.getenv("CLIENT_ID");
        String clientSecret = System.getenv("CLIENT_SECRET");
        String appName = System.getenv("OPTIMIZELY_APP_NAME");
        String appEnv = System.getenv("OPTIMIZELY_APP_ENV");

        log.info("Initializing Optimizely OpenFeature client. appName={}, appEnv={}", appName, appEnv);

        // Same flow as your sample repo
        ExperimentationServiceClient exchangeClient =
            new AvajeExperimentationServiceClient(
                new ExperimentationServiceApi.Builder()
                    .clientId(clientId)
                    .clientSecret(clientSecret)
                    .baseUrl("https://api-it.cloud.capitalone.com")
                    .build()
            );

        CofOptimizelyOptions options = CofOptimizelyOptions.builder()
            .appName(appName)
            .appEnv(appEnv)
            .xUpstreamEnv("non-ease")
            .experimentationServiceClient(exchangeClient)
            .simpleCache()
            .build();

        CofOptimizelyProvider provider = new CofOptimizelyProvider(options);

        OpenFeatureAPI openFeatureAPI = OpenFeatureAPI.getInstance();
        openFeatureAPI.setProviderAndWait(provider);

        log.info("Optimizely OpenFeature provider initialized successfully.");

        return openFeatureAPI.getClient();
    }
}


src/main/java/com/capitalone/api/deposits/promotions/service/FeatureFlagStartupPrinter.java

package com.capitalone.api.deposits.promotions.service;

import dev.openfeature.sdk.Client;
import dev.openfeature.sdk.EvaluationContext;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

// Use the same evaluation-context builder import from your sample repo.

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
            EvaluationContext context = CofEvaluationContextBuilder.builder()
                .entityId("12345")
                .build();

            boolean flagValue = client.getBooleanValue(FLAG_KEY, false, context);

            log.info("Optimizely flag [{}] resolved to [{}]", FLAG_KEY, flagValue);
        } catch (Exception e) {
            log.error("Failed to evaluate Optimizely flag at startup", e);
        }
    }
}


export CLIENT_ID=<your-client-id>
export CLIENT_SECRET=<your-client-secret>
export OPTIMIZELY_APP_NAME=<your-optimizely-app-name>
export OPTIMIZELY_APP_ENV=<your-optimizely-app-env>


  mvn clean compile

mvn spring-boot:run


///////////////////////////////

