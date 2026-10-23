import sys
from pathlib import Path
import pandas as pd
import numpy as np
import yaml

#universal reader of files (tiny func)
def read_yaml(file_path):
    with open(file_path, encoding="utf-8") as file:
        return pd.DataFrame(yaml.safe_load(file))

pd.read_yaml = read_yaml

def read(file_path):
    ext = Path(file_path).suffix.lower()[1:]
    return getattr(pd, f"read_{ext}")(file_path)


#table cleaning
NULLS = {'nan': np.nan, 'None': np.nan, 'NULL': np.nan, '': np.nan}

def clean_text(s):
    return s.astype(str).str.strip().str.replace(r'\s+', ' ', regex=True).replace(NULLS)

def clean_books(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.lstrip(':')
    df['title'] = clean_text(df['title'])
    #sort authors (afther a commen in chat)
    df['author'] = clean_text(df['author']).dropna().apply(
        lambda x: ", ".join(sorted([a.strip() for a in x.split(",")]))
    )
    df['year'] = pd.to_numeric(df['year'], errors='coerce').astype('Int64')
    return df

def clean_users(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ['name', 'address', 'email']:
        df[col] = clean_text(df[col])
    df['email'] = df['email'].str.lower()
    df.loc[~df['email'].str.contains('@', na=False), 'email'] = np.nan
    #clearing diffirnet char in phone numb, empty ones must be real NaN
    df['phone'] = df['phone'].astype(str).str.replace(r'\D', '', regex=True).replace({'': np.nan})
    return df

def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    #first digit group = dollars, second = cents  (€22¢25 -> 22.25, 29€50¢ -> 29.50, $ 35 -> 35.0)
    raw = df['unit_price'].astype(str)
    is_euro = raw.str.contains('€|EUR', case=False, na=False)
    parts = raw.str.extract(r'(\d+)(?:\D+(\d+))?')
    price = pd.to_numeric(parts[0] + '.' + parts[1].fillna('0'), errors='coerce')
    #everything to usd (1 eur = 1.2 usd)
    df['unit_price'] = np.where(is_euro, price * 1.2, price).round(2)
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').astype('Int64')
    df['paid_price'] = (df['quantity'] * df['unit_price']).round(2)

    #clearing datastamp and splitting
    clean_ts = (
        df['timestamp'].astype(str)
        .str.replace('A.M.', 'AM', regex=False)
        .str.replace('P.M.', 'PM', regex=False)
        .str.replace(r'[;,]', ' ', regex=True)
    )
    df['timestamp'] = pd.to_datetime(clean_ts, format='mixed', errors='coerce')
    df['date'] = df['timestamp'].dt.date
    df['year'] = df['timestamp'].dt.year
    df['month'] = df['timestamp'].dt.month
    df['day'] = df['timestamp'].dt.day

    df['shipping'] = clean_text(df['shipping'])
    return df


#ENTITY RESOLUTION (clearing / merge)
USER_FIELDS = ['name', 'address', 'phone', 'email']
#task says only one field can change -> same user if 3 of 4 fields are equal
USER_KEYS = [[c for c in USER_FIELDS if c != changed] for changed in USER_FIELDS]

def resolve_duplicates(books: pd.DataFrame, users: pd.DataFrame, orders: pd.DataFrame):
    books, users, orders = books.copy(), users.copy(), orders.copy()

    #books = mapping same title and author set to one id
    key = books[['title', 'author']].apply(lambda s: s.str.lower())
    books['canonical_id'] = books.groupby([key['title'], key['author']], dropna=False)['id'].transform('min')
    book_id_map = dict(zip(books['id'], books['canonical_id']))
    orders['book_id'] = orders['book_id'].map(book_id_map).fillna(orders['book_id'])
    books_dedup = books.sort_values('id').drop_duplicates(subset=['canonical_id']).drop(columns=['canonical_id'])

    #users = min id of the group wins, repeat until nothing changes (chained matches)
    match = users[USER_FIELDS].apply(lambda s: s.str.lower())
    match['id'] = users['id']
    user_id_map = {uid: uid for uid in users['id']}
    changed = True
    while changed:
        changed = False
        match['canon_id'] = match['id'].map(user_id_map)
        for cols in USER_KEYS:
            valid = match.dropna(subset=cols)
            group_min = valid.groupby(cols)['canon_id'].transform('min')
            better = group_min < valid['canon_id']
            if better.any():
                changed = True
                user_id_map.update(dict(zip(valid.loc[better, 'id'], group_min[better])))
                match['canon_id'] = match['id'].map(user_id_map)

    users['original_id'] = users['id']
    users['id'] = users['id'].map(user_id_map)
    orders['user_id'] = orders['user_id'].map(user_id_map).fillna(orders['user_id'])

    #keep old ids as aliases for the question 4
    aliases = users.groupby('id')['original_id'].agg(lambda s: sorted(s)).rename('aliases')
    users_dedup = (users.sort_values('original_id').drop_duplicates(subset=['id'])
                   .drop(columns=['original_id']).merge(aliases, left_on='id', right_index=True))

    return books_dedup, users_dedup, orders


#solution of question in one function
def analyze_store_data(books: pd.DataFrame, users: pd.DataFrame, orders: pd.DataFrame):

    # 1. Top 5 days by revenue (Format: "YYYY-MM-dd")
    daily_rev = orders.groupby('date')['paid_price'].sum().reset_index()
    daily_rev['date_str'] = pd.to_datetime(daily_rev['date']).dt.strftime('%Y-%m-%d')
    top_5_days = daily_rev.sort_values(by='paid_price', ascending=False).head(5)

    # 2. Number of unique users
    unique_users_count = users['id'].nunique()

    # 3. Number of unique sets of authors
    unique_author_sets = books['author'].dropna().str.lower().nunique()

    # 4. Most popular author(s) by sold book count
    merged_orders = orders.merge(books[['id', 'author']], left_on='book_id', right_on='id', suffixes=('_order', '_book'))
    author_sales = merged_orders.groupby('author')['quantity'].sum()
    top_authors = author_sales[author_sales == author_sales.max()].index.tolist()

    # 5. Top customer by total spending with all alias ids
    customer_spending = orders.groupby('user_id')['paid_price'].sum()
    top_user_id = customer_spending.idxmax()
    all_aliases = users.set_index('id').loc[top_user_id, 'aliases']

    return {
        "top_5_days": top_5_days[['date_str', 'paid_price']].values.tolist(),
        "unique_users": unique_users_count,
        "unique_author_sets": unique_author_sets,
        "top_authors": top_authors,
        "top_buyer": {"id": top_user_id, "spending": customer_spending.max(), "aliases": all_aliases},
        "daily_rev_df": daily_rev
    }

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "STORE1"

    books = clean_books(read(f"{folder}/books.yaml"))
    users = clean_users(read(f"{folder}/users.csv"))
    orders = clean_orders(read(f"{folder}/orders.parquet"))

    books_clean, users_clean, orders_clean = resolve_duplicates(books, users, orders)

    results = analyze_store_data(books_clean, users_clean, orders_clean)

    print("\n Analis of Result ")
    print("1. Top 5 Days by Revenue:")
    for d, rev in results["top_5_days"]:
        print(f"   {d} -> ${rev:,.2f}")

    print(f"\n2.Unique Users: {results['unique_users']}")
    print(f"3.Unique Author Sets: {results['unique_author_sets']}")
    print(f"4.Most Popular Author(s): {results['top_authors']}")
    print(f"5.Top Customer ID: {results['top_buyer']['id']} (Spending: ${results['top_buyer']['spending']:,.2f}) aliases: {results['top_buyer']['aliases']}")