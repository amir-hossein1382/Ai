import requests
import os
import time
import json
import logging
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
NOBITEX_TOKEN = os.getenv("NOBITEX_TOKEN")
RAMZINEX_API_KEY = os.getenv("RAMZINEX_API_KEY")
TABDEAL_API_KEY = os.getenv("TABDEAL_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
INITIAL_BALANCE = 4_000_000
SYMBOL = "USDTIRT"

WALLETS = {'nobitex': 500, 'ramzinex': 500, 'tabdeal': 500}

def save_wallets():
    try:
        with open('wallets.json', 'w') as f:
            json.dump(WALLETS, f)
        logger.info("موجودی‌ها ذخیره شدند.")
    except Exception as e:
        logger.error(f"خطا در ذخیره موجودی‌ها: {e}")

def load_wallets():
    global WALLETS
    try:
        with open('wallets.json', 'r') as f:
            WALLETS = json.load(f)
        logger.info("موجودی‌ها بارگذاری شدند.")
    except FileNotFoundError:
        logger.info("فایل موجودی‌ها یافت نشد.")
    except Exception as e:
        logger.error(f"خطا در بارگذاری موجودی‌ها: {e}")

def get_nobitex():
    headers = {"Authorization": f"Token {NOBITEX_TOKEN}"}
    for attempt in range(3):
        try:
            r = requests.get(f"https://api.nobitex.ir/market/stats/?symbol={SYMBOL.lower()}", headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()['stats'][SYMBOL.lower()]
            return {'name': 'nobitex', 'buy': float(data['bestBuy']), 'sell': float(data['bestSell']), 'fee': 0.002, 'url': 'https://nobitex.ir/market/USDTIRT'}
        except Exception as e:
            logger.error(f"خطا در nobitex (تلاش {attempt+1}): {e}")
            time.sleep(2)
    return None

def get_ramzinex():
    headers = {"Authorization": RAMZINEX_API_KEY}
    for attempt in range(3):
        try:
            r = requests.get("https://publicapi.ramzinex.com/exchange/api/v1.0/exchange/orderbooks/32", headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()['data']
            return {'name': 'ramzinex', 'buy': float(data['buy'][0]['price']), 'sell': float(data['sell'][0]['price']), 'fee': 0.0015, 'url': 'https://ramzinex.com/exchange/USDT-IRR'}
        except Exception as e:
            logger.error(f"خطا در ramzinex (تلاش {attempt+1}): {e}")
            time.sleep(2)
    return None

def get_tabdeal():
    headers = {"Authorization": f"Bearer {TABDEAL_API_KEY}"}
    for attempt in range(3):
        try:
            r = requests.get(f"https://api.tabdeal.org/v1/market/orderbook?symbol={SYMBOL}", headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()['data']
            return {'name': 'tabdeal', 'buy': float(data['bids'][0][0]), 'sell': float(data['asks'][0][0]), 'fee': 0.002, 'url': 'https://tabdeal.org/markets/usdt-irt'}
        except Exception as e:
            logger.error(f"خطا در tabdeal (تلاش {attempt+1}): {e}")
            time.sleep(2)
    return None

def fetch_prices():
    exchanges = [get_nobitex(), get_ramzinex(), get_tabdeal()]
    valid_exchanges = [ex for ex in exchanges if ex is not None]
    if len(valid_exchanges) < len(exchanges):
        failed_exchanges = ['nobitex' if ex is None else 'ramzinex' if ex is None else 'tabdeal' for ex in exchanges if ex is None]
        try:
            bot.send_message(chat_id=CHAT_ID, text=f"⚠️ خطا در دریافت داده از: {', '.join(failed_exchanges)}")
        except Exception as e:
            logger.error(f"خطا در ارسال اعلان تلگرام: {e}")
    return valid_exchanges

def check_balance_and_update(buy_ex, sell_ex, usdt_amount):
    if WALLETS[buy_ex] >= usdt_amount:
        WALLETS[buy_ex] -= usdt_amount
        WALLETS[sell_ex] += usdt_amount
        save_wallets()
        return True
    logger.warning(f"موجودی کافی در {buy_ex} نیست: {WALLETS[buy_ex]} تتر")
    return False

def calculate_arbitrage(prices):
    best_buy = min(prices, key=lambda x: x['buy'])
    best_sell = max(prices, key=lambda x: x['sell'])
    usdt_amount = INITIAL_BALANCE / best_buy['buy']
    gross_sell = usdt_amount * best_sell['sell']
    net_profit = gross_sell * (1 - best_sell['fee']) - INITIAL_BALANCE * (1 + best_buy['fee'])
    return {
        'buy_from': best_buy,
        'sell_to': best_sell,
        'net_profit': net_profit,
        'profit_percent': (net_profit / INITIAL_BALANCE) * 100,
        'usdt_amount': usdt_amount,
        'buy_ex': best_buy['name'],
        'sell_ex': best_sell['name']
    }

def send_signal(arb):
    if arb['profit_percent'] >= 1.5 and arb['usdt_amount'] >= 100:
        if check_balance_and_update(arb['buy_from']['name'], arb['sell_to']['name'], arb['usdt_amount']):
            msg = (
                "🚀 سیگنال آربیتراژ تتر\n"
                f"💰 سرمایه: {INITIAL_BALANCE:,} تومان\n"
                f"🔻 خرید از {arb['buy_from']['name']}: {arb['buy_from']['buy']:,} تومان\n"
                f"🔺 فروش در {arb['sell_to']['name']}: {arb['sell_to']['sell']:,} تومان\n"
                f"📊 مقدار تتر: {arb['usdt_amount']:.2f}\n"
                f"💵 سود خالص: {arb['net_profit']:,.0f} تومان ({arb['profit_percent']:.2f}%)\n"
                "⏳ مدت اعتبار: کوتاه مدت"
            )
            keyboard = [
                [InlineKeyboardButton(f"خرید از {arb['buy_from']['name']}", url=arb['buy_from']['url'])],
                [InlineKeyboardButton(f"فروش در {arb['sell_to']['name']}", url=arb['sell_to']['url'])],
                [InlineKeyboardButton("نمودار زنده", url="https://www.tradingview.com/chart/")]
            ]
            try:
                bot.send_message(chat_id=CHAT_ID, text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                logger.info(f"سیگنال ارسال شد: سود {arb['profit_percent']:.2f}%")
            except Exception as e:
                logger.error(f"خطا در ارسال سیگنال: {e}")
        else:
            logger.warning("موجودی کافی برای انجام آربیتراژ وجود ندارد.")
    else:
        logger.info(f"سود کم است: {arb['profit_percent']:.2f}% یا مقدار تتر کمتر از ۱۰۰")

def main():
    logger.info("ربات آربیتراژ شروع به کار کرد...")
    load_wallets()
    while True:
        try:
            prices = fetch_prices()
            if len(prices) < 2:
                logger.warning("داده کافی از صرافی‌ها دریافت نشد.")
            else:
                arb = calculate_arbitrage(prices)
                send_signal(arb)
            time.sleep(300)
        except Exception as e:
            logger.error(f"خطا در حلقه اصلی: {e}")
            time.sleep(60)

if __name__ == '__main__':
    main()
