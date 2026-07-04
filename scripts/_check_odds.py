import pandas as pd

df = pd.read_csv("https://github.com/nflverse/nfldata/raw/master/data/games.csv")
for season in [2024, 2025, 2026]:
    for gt in ["REG", "WC", "DIV", "CON", "SB"]:
        s = df[(df.season == season) & (df.game_type == gt)]
        if len(s) == 0:
            continue
        full = (
            s["spread_line"].notna()
            & s["total_line"].notna()
            & s["away_moneyline"].notna()
            & s["home_moneyline"].notna()
        ).sum()
        print(f"{season} {gt}: {len(s)} games, full odds: {full}")