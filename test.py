from curl_cffi import requests
import re
import jsbeautifier
from bs4 import BeautifulSoup

def fetch_flexy_script():
    url = 'https://flexy.stream/emb/zqohsuekv085'
    print('[*] Impersonating browser...')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://flexy.stream/'
    }
    print(f'[*] Fetching URL: {url}')
    resp = requests.get(url, headers=headers, impersonate='chrome')
    print(f'[*] Received response status: {resp.status_code}')

    soup = BeautifulSoup(resp.text, "html.parser")

    for script in soup.find_all("script"):
        if "eval(function(p,a,c,k,e,d)" in script.text:
            data_js = jsbeautifier.beautify(script.text)
            match = re.search(r'sources:\s*\[\{\s*src:\s*"([^"]+)"', data_js)

            if match:
                return match.group(1)
            
            else:
                print('[!] No .m3u8 URL found in the script')
                return None

if __name__ == '__main__':
    script = fetch_flexy_script()
    if script:
        print(script)
        print('[*] Script retrieved successfully')
    else:
        print('[!] Script not found')