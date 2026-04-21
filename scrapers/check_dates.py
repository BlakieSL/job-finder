"""Check what date fields JustJoinIT API exposes."""
import sys, io, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

HEADERS = {
    'x-api-version': '1',
    'accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
}

params = [
    ('categories', 'java'),
    ('city', 'Warszawa'),
    ('from', 0),
    ('itemsCount', 1),
    ('orderBy', 'descending'),
    ('sortBy', 'publishedAt'),
]

r = requests.get('https://justjoin.it/api/candidate-api/offers', headers=HEADERS, params=params)
data = r.json()
offer = data['data'][0]

print("=== List offer keys ===")
print(sorted(offer.keys()))

for k, v in sorted(offer.items()):
    kl = k.lower()
    if any(x in kl for x in ['date', 'time', 'publish', 'creat', 'expire', 'post', 'added', 'renewed']):
        print(f"  ** {k} = {v}")

# Detail
slug = offer['slug']
print(f"\n=== Detail keys for {slug} ===")
r2 = requests.get(f'https://justjoin.it/api/candidate-api/offers/{slug}', headers=HEADERS)
detail = r2.json()
print(sorted(detail.keys()))

for k, v in sorted(detail.items()):
    kl = k.lower()
    if any(x in kl for x in ['date', 'time', 'publish', 'creat', 'expire', 'post', 'added', 'renewed']):
        print(f"  ** {k} = {v}")
