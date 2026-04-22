#!/usr/bin/env python3
"""
Price Fetching Module
Retrieves live and historical prices for stocks and cryptocurrencies
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
from portfolio import Portfolio

CACHE_FILE = os.path.join(os.path.dirname(__file__), "price_cache.json")
CACHE_DURATION_MINUTES = 5
CACHE_DURATION_MINUTES_HISTORICAL = 1440  # 24 hours for historical data

# Finnhub API configuration
FINNHUB_API_KEY = "d3r63jhr01qopgh74tlgd3r63jhr01qopgh74tm0"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# Alpha Vantage API configuration
ALPHAVANTAGE_API_KEY = "HJUI1TZ5H1QTYU4D"
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"


class PriceCache:
    def __init__(self):
        self.cache = self.load_cache()

    def load_cache(self) -> Dict:
        """Load price cache from file"""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                return {}
        return {}

    def save_cache(self) -> None:
        """Save price cache to file"""
        with open(CACHE_FILE, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def get(self, key: str, cache_duration_minutes: int = None) -> Optional[Dict]:
        """Get cached price if still valid"""
        if cache_duration_minutes is None:
            cache_duration_minutes = CACHE_DURATION_MINUTES

        if key in self.cache:
            cached = self.cache[key]
            cache_time = datetime.fromisoformat(cached['timestamp'])
            if datetime.now() - cache_time < timedelta(minutes=cache_duration_minutes):
                return cached
        return None

    def set(self, key: str, value: Dict) -> None:
        """Set cached price with timestamp"""
        value['timestamp'] = datetime.now().isoformat()
        self.cache[key] = value
        self.save_cache()


price_cache = PriceCache()


def get_stock_price(symbol: str, use_cache: bool = True) -> Dict:
    """
    Get current stock price using Finnhub API

    Args:
        symbol: Stock ticker symbol
        use_cache: Whether to use cached prices

    Returns:
        Dictionary with price information
    """
    symbol = symbol.upper()
    cache_key = f"stock_{symbol}"

    # Check cache first
    if use_cache:
        cached = price_cache.get(cache_key)
        if cached:
            return cached

    try:
        # Get real-time quote from Finnhub
        url = f"{FINNHUB_BASE_URL}/quote"
        params = {
            'symbol': symbol,
            'token': FINNHUB_API_KEY
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        # Check if we got valid data
        if data.get('c', 0) > 0:  # 'c' is current price
            current_price = float(data['c'])
            previous_close = float(data.get('pc', current_price))
            change = float(data.get('d', 0))  # 'd' is change
            change_percent = float(data.get('dp', 0))  # 'dp' is percent change

            result = {
                'symbol': symbol,
                'price': current_price,
                'change': change,
                'change_percent': f"{change_percent:.2f}%",
                'previous_close': previous_close,
                'high': float(data.get('h', 0)),
                'low': float(data.get('l', 0)),
                'open': float(data.get('o', 0)),
                'source': 'finnhub',
                'timestamp': datetime.now().isoformat()
            }
        else:
            # Fallback to Yahoo Finance if Finnhub doesn't have data
            result = get_stock_price_yahoo(symbol)

        if result.get('price', 0) > 0:
            price_cache.set(cache_key, result)
        return result

    except Exception as e:
        # Fallback to Yahoo Finance on error
        try:
            result = get_stock_price_yahoo(symbol)
            if result.get('price', 0) > 0:
                price_cache.set(cache_key, result)
            return result
        except:
            return {
                'symbol': symbol,
                'error': str(e),
                'price': 0,
                'timestamp': datetime.now().isoformat()
            }


def get_stock_price_yahoo(symbol: str) -> Dict:
    """
    Fallback method using Yahoo Finance

    Args:
        symbol: Stock ticker symbol

    Returns:
        Dictionary with price information
    """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {'interval': '1d', 'range': '1d'}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        quote = data['chart']['result'][0]['meta']
        return {
            'symbol': symbol,
            'price': float(quote.get('regularMarketPrice', 0)),
            'change': float(quote.get('regularMarketPrice', 0) - quote.get('previousClose', 0)),
            'change_percent': f"{((quote.get('regularMarketPrice', 0) / quote.get('previousClose', 1) - 1) * 100):.2f}%",
            'volume': int(quote.get('regularMarketVolume', 0)),
            'source': 'yahoo',
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'symbol': symbol,
            'error': str(e),
            'price': 0,
            'timestamp': datetime.now().isoformat()
        }


def get_crypto_price(symbol: str, use_cache: bool = True) -> Dict:
    """
    Get current cryptocurrency price using CoinGecko API (free, no key required)

    Args:
        symbol: Crypto symbol (BTC, ETH, etc.)
        use_cache: Whether to use cached prices

    Returns:
        Dictionary with price information
    """
    symbol = symbol.upper()
    cache_key = f"crypto_{symbol}"

    # Check cache first
    if use_cache:
        cached = price_cache.get(cache_key)
        if cached:
            return cached

    # Map common symbols to CoinGecko IDs
    symbol_map = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'USDT': 'tether',
        'BNB': 'binancecoin',
        'SOL': 'solana',
        'ADA': 'cardano',
        'XRP': 'ripple',
        'DOT': 'polkadot',
        'DOGE': 'dogecoin',
        'AVAX': 'avalanche-2',
        'MATIC': 'matic-network',
        'LINK': 'chainlink',
        'UNI': 'uniswap',
        'ATOM': 'cosmos',
        'LTC': 'litecoin'
    }

    coin_id = symbol_map.get(symbol, symbol.lower())

    try:
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': 'usd',
            'include_24hr_change': 'true',
            'include_24hr_vol': 'true'
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if coin_id in data:
            coin_data = data[coin_id]
            result = {
                'symbol': symbol,
                'price': float(coin_data.get('usd', 0)),
                'change_24h': float(coin_data.get('usd_24h_change', 0)),
                'change_percent': f"{coin_data.get('usd_24h_change', 0):.2f}%",
                'volume_24h': float(coin_data.get('usd_24h_vol', 0)),
                'source': 'coingecko',
                'timestamp': datetime.now().isoformat()
            }
        else:
            result = {
                'symbol': symbol,
                'error': 'Cryptocurrency not found',
                'price': 0,
                'timestamp': datetime.now().isoformat()
            }

        price_cache.set(cache_key, result)
        return result

    except Exception as e:
        return {
            'symbol': symbol,
            'error': str(e),
            'price': 0,
            'timestamp': datetime.now().isoformat()
        }


def get_historical_prices(symbol: str, days: int = 30, asset_type: str = "stock") -> Dict:
    """
    Get historical price data

    Args:
        symbol: Ticker/crypto symbol
        days: Number of days of historical data
        asset_type: Type of asset (stock or crypto)

    Returns:
        Dictionary with historical prices
    """
    symbol = symbol.upper()

    if asset_type.lower() == "crypto":
        return get_crypto_historical(symbol, days)
    else:
        return get_stock_historical(symbol, days)


def get_stock_historical(symbol: str, days: int) -> Dict:
    """Get historical stock prices - Alpha Vantage primary"""
    # Check cache first (24-hour cache for historical data)
    cache_key = f"historical_{symbol}_{days}"
    cached = price_cache.get(cache_key, cache_duration_minutes=CACHE_DURATION_MINUTES_HISTORICAL)
    if cached:
        return cached

    # Try Alpha Vantage first, fallback to Yahoo Finance
    try:
        result = get_stock_historical_alphavantage(symbol, days)
        if 'error' not in result and result.get('prices'):
            price_cache.set(cache_key, result)
            return result
        # Fallback to Yahoo if Alpha Vantage fails
        result = get_stock_historical_yahoo(symbol, days)
        if 'error' not in result and result.get('prices'):
            price_cache.set(cache_key, result)
        return result
    except Exception as e:
        return {
            'symbol': symbol,
            'error': str(e),
            'prices': [],
            'timestamp': datetime.now().isoformat()
        }


def get_stock_historical_alphavantage(symbol: str, days: int) -> Dict:
    """Get historical stock prices from Alpha Vantage"""
    import time
    try:
        # Alpha Vantage uses outputsize: compact (100 days) or full (20+ years)
        outputsize = 'compact' if days <= 100 else 'full'

        url = ALPHAVANTAGE_BASE_URL
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': symbol,
            'apikey': ALPHAVANTAGE_API_KEY,
            'outputsize': outputsize
        }

        # Add delay to avoid rate limiting (5 calls/minute for free tier)
        # In practice, Alpha Vantage is often more lenient, so use 3 seconds
        time.sleep(3)

        response = requests.get(url, params=params, timeout=15)

        # Check for rate limiting
        if response.status_code == 429:
            raise Exception("Rate limited by Alpha Vantage")

        data = response.json()

        # Check for API error messages
        if 'Error Message' in data:
            raise Exception(data['Error Message'])

        if 'Note' in data:
            raise Exception("Alpha Vantage API rate limit reached")

        # Extract time series data
        time_series_key = 'Time Series (Daily)'
        if time_series_key not in data:
            raise Exception("No time series data in response")

        time_series = data[time_series_key]

        # Convert to our format
        prices = []
        sorted_dates = sorted(time_series.keys(), reverse=True)[:days]

        for date in reversed(sorted_dates):
            day_data = time_series[date]
            prices.append({
                'date': date,
                'open': float(day_data['1. open']),
                'high': float(day_data['2. high']),
                'low': float(day_data['3. low']),
                'close': float(day_data['4. close']),
                'volume': int(day_data['5. volume'])
            })

        return {
            'symbol': symbol,
            'prices': prices,
            'source': 'alphavantage',
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'symbol': symbol,
            'error': str(e),
            'prices': [],
            'timestamp': datetime.now().isoformat()
        }


def get_stock_historical_yahoo(symbol: str, days: int) -> Dict:
    """Get historical stock prices from Yahoo Finance (fallback)"""
    import time
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {
            'interval': '1d',
            'period1': int(start_date.timestamp()),
            'period2': int(end_date.timestamp())
        }

        # Add delay to avoid rate limiting
        time.sleep(0.5)

        response = requests.get(url, params=params, timeout=10)

        # Check for rate limiting
        if response.status_code == 429:
            raise Exception("Rate limited by Yahoo Finance")

        # Check if response is valid JSON
        if not response.text or response.text.startswith('Edge:'):
            raise Exception("Invalid response from Yahoo Finance")

        data = response.json()

        result_data = data['chart']['result'][0]
        timestamps = result_data['timestamp']
        quotes = result_data['indicators']['quote'][0]

        prices = []
        for i, ts in enumerate(timestamps):
            prices.append({
                'date': datetime.fromtimestamp(ts).strftime('%Y-%m-%d'),
                'open': quotes['open'][i],
                'high': quotes['high'][i],
                'low': quotes['low'][i],
                'close': quotes['close'][i],
                'volume': quotes['volume'][i]
            })

        return {
            'symbol': symbol,
            'prices': prices,
            'source': 'yahoo',
            'timestamp': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'symbol': symbol,
            'error': str(e),
            'prices': [],
            'timestamp': datetime.now().isoformat()
        }


def get_crypto_historical(symbol: str, days: int) -> Dict:
    """Get historical crypto prices from CoinGecko"""
    # Check cache first (24-hour cache for historical data)
    cache_key = f"historical_crypto_{symbol}_{days}"
    cached = price_cache.get(cache_key, cache_duration_minutes=CACHE_DURATION_MINUTES_HISTORICAL)
    if cached:
        return cached

    symbol_map = {
        'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether',
        'BNB': 'binancecoin', 'SOL': 'solana', 'ADA': 'cardano',
        'XRP': 'ripple', 'DOT': 'polkadot', 'DOGE': 'dogecoin'
    }

    coin_id = symbol_map.get(symbol, symbol.lower())

    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {
            'vs_currency': 'usd',
            'days': days,
            'interval': 'daily'
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        prices = []
        for price_data in data.get('prices', []):
            prices.append({
                'date': datetime.fromtimestamp(price_data[0] / 1000).strftime('%Y-%m-%d'),
                'price': price_data[1]
            })

        result = {
            'symbol': symbol,
            'prices': prices,
            'source': 'coingecko',
            'timestamp': datetime.now().isoformat()
        }

        # Cache the result
        price_cache.set(cache_key, result)
        return result

    except Exception as e:
        return {
            'symbol': symbol,
            'error': str(e),
            'prices': [],
            'timestamp': datetime.now().isoformat()
        }


def update_all_prices() -> Dict:
    """
    Update current prices for all assets in the portfolio

    Returns:
        Dictionary with update results
    """
    portfolio = Portfolio()
    assets = portfolio.list_assets()

    results = {
        'updated': [],
        'errors': [],
        'timestamp': datetime.now().isoformat()
    }

    for asset in assets:
        symbol = asset['symbol']
        asset_type = asset['asset_type']

        try:
            if asset_type == 'crypto':
                price_data = get_crypto_price(symbol)
            else:
                price_data = get_stock_price(symbol)

            if 'error' not in price_data and price_data['price'] > 0:
                portfolio.update_asset_price(symbol, price_data['price'])
                results['updated'].append({
                    'symbol': symbol,
                    'price': price_data['price']
                })
            else:
                results['errors'].append({
                    'symbol': symbol,
                    'error': price_data.get('error', 'Unknown error')
                })

        except Exception as e:
            results['errors'].append({
                'symbol': symbol,
                'error': str(e)
            })

    portfolio.save_portfolio()
    return results


def main():
    """Command line interface for testing"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python prices.py [stock|crypto|historical|update] SYMBOL [DAYS]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "stock":
        if len(sys.argv) < 3:
            print("Usage: python prices.py stock SYMBOL")
            sys.exit(1)
        result = get_stock_price(sys.argv[2])
        print(json.dumps(result, indent=2))

    elif command == "crypto":
        if len(sys.argv) < 3:
            print("Usage: python prices.py crypto SYMBOL")
            sys.exit(1)
        result = get_crypto_price(sys.argv[2])
        print(json.dumps(result, indent=2))

    elif command == "historical":
        if len(sys.argv) < 4:
            print("Usage: python prices.py historical SYMBOL ASSET_TYPE [DAYS]")
            sys.exit(1)
        symbol = sys.argv[2]
        asset_type = sys.argv[3]
        days = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        result = get_historical_prices(symbol, days, asset_type)
        print(json.dumps(result, indent=2))

    elif command == "update":
        result = update_all_prices()
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
