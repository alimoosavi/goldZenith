import requests

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
def main():
    ticker_no = 'عیار'
    r = requests.get(f'http://old.tsetmc.com/tsev2/data/InstTradeHistory.aspx?i={ticker_no}&Top=999999&A=0', headers=headers)
    print(r.text.split(';'))

if __name__ == '__main__':
    main()
