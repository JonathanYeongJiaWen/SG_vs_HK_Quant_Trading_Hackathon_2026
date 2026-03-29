import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode

class RoostooClient:
    def __init__(self, api_key: str, secret_key: str):
        self.base_url = "https://mock-api.roostoo.com"
        self.api_key = api_key
        self.secret_key = secret_key

    def _generate_signature(self, params: dict) -> tuple:
        """
        Generates HMAC SHA256 signature.
        Roostoo requires params to be sorted alphabetically and formatted as a query string.
        """
        query_string = urlencode(dict(sorted(params.items())), safe='/')
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature, query_string

    def _request(self, method: str, endpoint: str, params: dict = None, require_auth: bool = False):
        """
        Centralized request handler. Manages headers, signatures, and exception handling 
        so the bot doesn't crash on errors.
        """
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        headers = {}

        if require_auth:
            # Roostoo requires a 13-digit millisecond timestamp for auth
            params['timestamp'] = int(time.time() * 1000)
            signature, query_string = self._generate_signature(params)
            
            headers['RST-API-KEY'] = self.api_key
            headers['MSG-SIGNATURE'] = signature
            
            # API docs mandate this specific Content-Type for POST requests
            if method == 'POST':
                headers['Content-Type'] = 'application/x-www-form-urlencoded'

        try:
            if method == 'GET':
                response = requests.get(url, params=params, headers=headers, timeout=10)
            elif method == 'POST':
                # POST expects the URL-encoded string as the body
                data = query_string if require_auth else params
                response = requests.post(url, data=data, headers=headers, timeout=10)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            # Logs the error but allows the script to keep running
            print(f"Network or API Error at {endpoint}: {e}")
            return None

    def check_server_time(self):
        """GET /v3/serverTime - RCL_NoVerification level"""
        return self._request('GET', '/v3/serverTime')

    def get_ticker(self, pair: str = None):
        """GET /v3/ticker - RCL_TSCheck level"""
        params = {'pair': pair} if pair else {}
        params['timestamp'] = int(time.time() * 1000)
        return self._request('GET', '/v3/ticker', params=params)

    def get_balance(self):
        """GET /v3/balance - RCL_TopLevelCheck level (Requires Auth)"""
        return self._request('GET', '/v3/balance', require_auth=True)

    def place_order(self, pair: str, side: str, order_type: str, quantity: float, price: float = None):
        """POST /v3/place_order - RCL_TopLevelCheck level (Requires Auth)"""
        params = {
            'pair': pair,
            'side': side.upper(),       # 'BUY' or 'SELL'
            'type': order_type.upper(), # 'MARKET' or 'LIMIT'
            'quantity': str(quantity)   # Docs specify casting numericals to strings in params
        }
        if order_type.upper() == 'LIMIT' and price is not None:
            params['price'] = str(price)
            
        return self._request('POST', '/v3/place_order', params=params, require_auth=True)

    # --- NEW CLEANUP METHODS ---

    def get_open_orders(self, pair: str = None):
        """GET /v3/open_orders - RCL_TopLevelCheck level (Requires Auth)"""
        params = {}
        if pair:
            params['pair'] = pair
        return self._request('GET', '/v3/open_orders', params=params, require_auth=True)

    def cancel_order(self, order_id: str, pair: str = None):
        """POST /v3/cancel_order - RCL_TopLevelCheck level (Requires Auth)"""
        params = {'order_id': str(order_id)}
        if pair:
            params['pair'] = pair
        return self._request('POST', '/v3/cancel_order', params=params, require_auth=True)