filter accountId = "578930797225"
filter label(`^Load Balancer`) = "prod-offer-eligibility-alb"
filter metric ~ /^(RequestCount|HTTPCode_Target_4XX_Count)$/

timechart 5m,
  request_count:sum(if(metric = "RequestCount", value, 0)),
  target_4xx_count:sum(if(metric = "HTTPCode_Target_4XX_Count", value, 0))

make_col alb_4xx_error_rate:if(request_count = 0, 0.0, 100.0 * target_4xx_count / request_count)

pick_col timestamp, alb_4xx_error_rate


///////////////////////


filter accountId = "578930797225"
filter label(`^Load Balancer`) = "prod-offer-eligibility-alb"
filter metric = "RequestCount"

timechart 5m,
  alb_request_count:sum(value)

pick_col timestamp, alb_request_count
