import pandas as pd

df = pd.read_parquet('data/orderbooks/IRTKLOTF0001_1403-12-01.parquet')
print(df.head(100))
# print(df.info())