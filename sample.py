package com.capitalone.api.deposits.promotions.configuration;

import com.capitalone.experimentationservice.api.ExperimentationServiceClient;
import com.capitalone.experimentationservice.api.avaje.AvajeExperimentationServiceClient;
import com.capitalone.experimentationservice.api.avaje.ExperimentationServiceApi;
import com.capitalone.openfeature.providers.CofOptimizelyOptions;
import com.capitalone.openfeature.providers.CofOptimizelyProvider;
import dev.openfeature.sdk.Client;
import dev.openfeature.sdk.OpenFeatureAPI;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OptimizelyOpenFeatureConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OptimizelyOpenFeatureConfiguration.class);

    @Bean
    public Client openFeatureClient() throws Exception {
        String clientId = System.getenv("CLIENT_ID");
        String clientSecret = System.getenv("CLIENT_SECRET");
        String appName = System.getenv("OPTIMIZELY_APP_NAME");
        String appEnv = System.getenv("OPTIMIZELY_APP_ENV");

        log.info("Initializing Optimizely OpenFeature client. appName={}, appEnv={}", appName, appEnv);

        ExperimentationServiceClient exchangeClient =
                new AvajeExperimentationServiceClient(
                        new ExperimentationServiceApi.Builder()
                                .clientId(clientId)
                                .clientSecret(clientSecret)
                                .baseUrl("https://api-it.cloud.capitalone.com")
                                .build());

        CofOptimizelyOptions options =
                CofOptimizelyOptions.builder()
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
