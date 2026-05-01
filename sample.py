Our consumer pact is now being generated, but can-i-deploy is failing because PactFlow says no provider version is currently recorded as deployed/released in the development environment.

Consumer:
asvofferfulfillmentengine-offerretroactiveonboard-bankoffersretroactiveonboard

Provider:
asvofferfulfillmentengine-offereligibilityapi-bankofferseligibilityapi-6.2

Environment:
development

Can you confirm whether the provider pipeline records deployment using:

pact-broker record-deployment --pacticipant asvofferfulfillmentengine-offereligibilityapi-bankofferseligibilityapi-6.2 --version <provider-version> --environment development

Also, can you confirm whether provider verification results are being published back to PactFlow for this consumer/provider pact?
