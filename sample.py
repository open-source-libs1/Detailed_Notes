curl -i -X POST "http://127.0.0.1:3000/protected/573828/offer/fulfillment/eligible" \
  -H "Content-Type: application/json" \
  -H "Client-Correlation-Id: 1233" \
  -H "X-Message-Id: 1233" \
  -H "Associate-Correlation-Id: sddsddd" \
  --data-raw '{
    "accountReferenceId": "YS4WJnZ1Gsfk/UbQ1Vi7NIAJUH0gR6GdHt72u++LKpE=",
    "customerReferenceId": "1I7qEYYahhObgp+5SCppdQ==",
    "productCode": "4000",
    "promotionCode": "REWARD250",
    "accountOpeningTimestamp": "2021-06-15T19:28:40Z"
  }'



//////////////////


curl -i -X POST "http://127.0.0.1:3000/protected/573828/offer/fulfillment/onboard" \
  -H "Content-Type: application/json" \
  -H "Client-Correlation-Id: 1233" \
  -H "X-Message-Id: 1233" \
  -H "Associate-Correlation-Id: sddsddd" \
  --data-raw '{
    "accountReferenceId": "YS4WJnZ1Gsfk/UbQ1Vi7NIAJUH0gR6GdHt72u++LKpE=",
    "customerReferenceId": "1I7qEYYahhObgp+5SCppdQ==",
    "productCode": "4000",
    "promotionCode": "REWARD250",
    "accountOpeningTimestamp": "2021-06-15T19:28:40Z"
  }'


    
////////////////////////

curl -i -X GET "http://127.0.0.1:3000/deposits/offer-management/customers/1I7qEYYahhObgp+5SCppdQ==/offers"


    
