query IntrospectDetailsArgs {
  __type(name: "TcExhibit") {
    name
    fields {
      name
      args { name type { kind name ofType { kind name ofType { kind name } } } }
    }
  }
}



///////////////


query IntrospectTcExhibitArgs {
  __type(name: "Rebates") {
    name
    fields {
      name
      args { name type { kind name ofType { kind name ofType { kind name } } } }
    }
  }
}



//////////////////


query GetTCExhibitData($uwReqId: String!, $scenarioId: String!, $indicator: String!, $gpi: String!) {
  rebates(indicator: $indicator) {
    tcExhibit(uwReqId: $uwReqId, scenarioId: $scenarioId) {
      uwReqId
      scenarioId
      details(gpi: $gpi) {
        gpi
        drugName
        grossPrice
        benchmarkPrice
        netPriceUnit
      }
      error
    }
  }
}
