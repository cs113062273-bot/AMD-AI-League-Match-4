"""Recognize explicit common currency codes; never infer exchange rates or convert values."""
CODES=('USD','EUR','GBP','TWD','JPY','CAD','AUD','CNY','CHF','HKD','SGD','NZD','INR','KRW',
       'SEK','NOK','DKK','BRL','MXN','ZAR','PLN','AED','SAR','CZK','HUF','ILS','IDR','MYR','THB','PHP','VND')
PATTERN='(?:'+'|'.join(CODES)+')'
