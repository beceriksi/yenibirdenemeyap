import ccxt
import pandas as pd
import requests
import time
import os
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("HATA: Telegram Token veya Chat ID bulunamadı!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}")

def check_market():
    exchange = ccxt.okx({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    try:
        exchange.load_markets()
        # Sadece USDT perpetual paritelerini al
        symbols = [s for s in exchange.symbols if s.endswith('/USDT:USDT')]
    except Exception as e:
        print(f"Piyasa verileri yüklenemedi: {e}")
        return

    # --- HİSSE SENEDİ VE ENDEKSLERİ ELEME FİLTRESİ ---
    # Geleneksel borsa hisseleri, endeksler veya kripto olmayan varlıkların ticker'ları buraya eklenir.
    stock_and_indices = ['NKE', 'OKTA', 'KR200', 'FWDI', 'DOOD', 'OPG', 'SKUU', 'VVV', 'ZKP']

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(symbols)} parite taranıyor (Hisseler filtreleniyor)...")

    signals_found = []

    for symbol in symbols:
        try:
            # Örn: "BTC/USDT:USDT" -> Base varlığı ayıkla ("BTC")
            base_currency = symbol.split('/')[0]
            
            # Eğer varlık hisse/endeks listesindeyse direkt atla
            if base_currency in stock_and_indices:
                continue

            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=40)
            if len(ohlcv) < 40:
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            last_close = df['close'].iloc[-2]
            last_open = df['open'].iloc[-2]
            last_volume = df['volume'].iloc[-2]
            
            avg_volume = df['volume'].iloc[-32:-2].mean()
            price_change_pct = ((last_close - last_open) / last_open) * 100
            
            # 3 Saatlik Yatay Sıkışma Kontrolü
            recent_high = df['high'].iloc[-13:-2].max()
            recent_low = df['low'].iloc[-13:-2].min()
            consolidation_range_pct = ((recent_high - recent_low) / recent_low) * 100
            is_tight_consolidation = consolidation_range_pct <= 3.5
            
            # Filtreler
            is_volume_spike = last_volume >= (avg_volume * 3.0)
            is_price_compressed = (price_change_pct >= 0.1) and (price_change_pct <= 1.5)
            is_green_candle = last_close > last_open
            
            if is_volume_spike and is_price_compressed and is_green_candle and is_tight_consolidation:
                fr_value = 0
                try:
                    funding_rate = exchange.fetch_funding_rate(symbol)
                    fr_value = funding_rate.get('fundingRate', 0) * 100
                except:
                    pass

                signals_found.append({
                    "symbol": symbol,
                    "volume_mult": f"{last_volume / avg_volume:.1f}",
                    "price_change": f"{price_change_pct:.2f}",
                    "consolidation": f"{consolidation_range_pct:.2f}",
                    "fr": f"{fr_value:.4f}"
                })
                print(f"Kripto sinyali sepete eklendi: {symbol}")
                
            time.sleep(exchange.rateLimit / 1000)
            
        except Exception as e:
            continue

    if signals_found:
        scan_time = datetime.now().strftime('%H:%M - %d.%m.%Y')
        message = (
            f"🎯 *KRİPTO PATLAMA RADARI - ÖZET RAPOR*\n"
            f"🕒 *Tarama Zamanı:* `{scan_time}`\n"
            f"⚡ *Tespit Edilen Kripto Fırsatı:* `{len(signals_found)} Adet`\n"
            f"-----------------------------------\n\n"
        )

        for s in signals_found:
            message += (
                f"📍 *Parite:* `{s['symbol']}`\n"
                f"📊 *Hacim Artışı:* Normalin `{s['volume_mult']}` katı\n"
                f"📈 *Mum Değişimi:* `+{s['price_change']}%` (Henüz patlamadı)\n"
                f"📐 *Sıkışma Aralığı:* `% {s['consolidation']}`\n"
                f"💰 *Funding Rate:* `% {s['fr']}`\n"
                f"-----------------------------------\n"
            )

        message += f"\n💡 *Analiz:* Sadece gerçek kripto paralar filtrelenmiştir. Tahtaları kontrol edin!"
        
        send_telegram_message(message)
        print("Kripto özet raporu Telegram'a gönderildi.")
    else:
        print("Bu taramada kriterlere uyan kripto coin bulunamadı.")

if __name__ == "__main__":
    check_market()
