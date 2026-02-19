import requests
import json
import base64
from datetime import datetime
from django.conf import settings
import random
import string


class MpesaClient:
    def __init__(self):
        self.consumer_key = settings.MPESA_CONSUMER_KEY
        self.consumer_secret = settings.MPESA_CONSUMER_SECRET
        self.passkey = settings.MPESA_PASSKEY
        self.shortcode = settings.MPESA_SHORTCODE
        self.environment = settings.MPESA_ENVIRONMENT

    def get_access_token(self):
        """Get M-Pesa access token - simulated for testing"""
        if settings.MPESA_SIMULATION_MODE:
            return "simulation_access_token_12345"

        # Real API call for production
        api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

        if self.environment == 'production':
            api_url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

        response = requests.get(api_url, auth=requests.auth.HTTPBasicAuth(
            self.consumer_key, self.consumer_secret))

        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            raise Exception(f"Failed to get access token: {response.text}")

    def stk_push(self, phone_number, amount, account_reference, transaction_desc, callback_url):
        """Initiate STK Push - simulated for testing"""

        # SIMULATION MODE - Return fake success response
        if settings.MPESA_SIMULATION_MODE:
            print(f"🔵 SIMULATION: M-Pesa STK Push to {phone_number} for KES {amount}")
            print(f"Account: {account_reference}, Description: {transaction_desc}")

            # Generate a fake CheckoutRequestID
            checkout_id = 'ws_CO_' + ''.join(random.choices(string.digits, k=10)) + '_' + ''.join(
                random.choices(string.ascii_uppercase + string.digits, k=13))

            return {
                "MerchantRequestID": "21605-" + ''.join(random.choices(string.digits, k=8)) + "-1",
                "CheckoutRequestID": checkout_id,
                "ResponseCode": "0",
                "ResponseDescription": "Success. Request accepted for processing",
                "CustomerMessage": "Success. Request accepted for processing"
            }

        # Real API call for production
        access_token = self.get_access_token()

        if self.environment == 'sandbox':
            api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        else:
            api_url = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(
            (self.shortcode + self.passkey + timestamp).encode()
        ).decode()

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),
            'PartyA': phone_number,
            'PartyB': self.shortcode,
            'PhoneNumber': phone_number,
            'CallBackURL': callback_url,
            'AccountReference': account_reference,
            'TransactionDesc': transaction_desc
        }

        response = requests.post(api_url, json=payload, headers=headers)
        return response.json()

    def query_status(self, checkout_request_id):
        """Query transaction status - simulated for testing"""

        # SIMULATION MODE - Return fake success response
        if settings.MPESA_SIMULATION_MODE:
            print(f"🔵 SIMULATION: Querying status for {checkout_request_id}")

            # 80% chance of success for testing
            if random.random() < 0.8:
                return {
                    "ResponseCode": "0",
                    "ResponseDescription": "The service request is processed successfully",
                    "MerchantRequestID": checkout_request_id.split('_')[0] if '_' in checkout_request_id else "21605",
                    "CheckoutRequestID": checkout_request_id,
                    "ResultCode": "0",
                    "ResultDesc": "The service request is processed successfully",
                    "MpesaReceiptNumber": "SIM" + ''.join(random.choices(string.digits, k=9))
                }
            else:
                return {
                    "ResponseCode": "0",
                    "ResponseDescription": "The service request is processed successfully",
                    "MerchantRequestID": checkout_request_id.split('_')[0] if '_' in checkout_request_id else "21605",
                    "CheckoutRequestID": checkout_request_id,
                    "ResultCode": "1",
                    "ResultDesc": "The balance is insufficient for the transaction"
                }

        # Real API call for production
        access_token = self.get_access_token()

        if self.environment == 'sandbox':
            api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"
        else:
            api_url = "https://api.safaricom.co.ke/mpesa/stkpushquery/v1/query"

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(
            (self.shortcode + self.passkey + timestamp).encode()
        ).decode()

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'CheckoutRequestID': checkout_request_id
        }

        response = requests.post(api_url, json=payload, headers=headers)
        return response.json()