"""Run backtesting on completed fixtures."""

import asyncio
import logging
from src.backtesting import run_full_backtest
from src.utils import ConfigManager

logging.basicConfig(level=logging.WARNING)


async def main():
    config = ConfigManager()
    settings = config.get_settings()

    all_results = []

    for league in ['spain_-_la_liga', 'germany_-_bundesliga', 'italy_-_serie_a', 'france_-_ligue_1', 'england_-_fa_cup']:
        print(f'\n=== Backtesting {league} ===')

        results = await run_full_backtest(
            api_key=settings.opticodds_api_key,
            league=league,
            min_edge=5.0,  # Lowered to find more bets
            min_odds=1.5,
            max_odds=5.0   # Increased to find more bets
        )

        print(f'Bets: {results.total_bets} | Wins: {results.wins} | Losses: {results.losses}')
        print(f'Win Rate: {results.win_rate:.1f}% | ROI: {results.roi:.1f}%')
        print(f'Profit: ${results.total_profit:.2f}')

        all_results.extend(results.bets)

        if results.bets:
            print('\nIndividual bets:')
            for bet in results.bets:
                status = 'WIN ' if bet.won else 'LOSS' if bet.won == False else 'PUSH'
                profit_str = f'+${bet.profit:.2f}' if bet.profit and bet.profit > 0 else f'-${abs(bet.profit):.2f}' if bet.profit else '$0'
                print(f'  [{status}] {bet.edge_percent:5.1f}% | {bet.book_odds:.2f} @ {bet.book_name:10} | {bet.selection:15} | {bet.market:25} | Actual: {bet.actual_result} | {profit_str}')

    # Summary
    print()
    print('=' * 70)
    print('COMBINED BACKTEST RESULTS')
    print('=' * 70)
    total_bets = len(all_results)
    settled = [b for b in all_results if b.won is not None]
    wins = sum(1 for b in settled if b.won == True)
    losses = sum(1 for b in settled if b.won == False)
    profit = sum(b.profit or 0 for b in settled)
    staked = len(settled) * 10

    print(f'Total Bets Found: {total_bets}')
    print(f'Settled: {len(settled)} | Wins: {wins} | Losses: {losses}')
    if settled:
        print(f'Win Rate: {(wins/len(settled))*100:.1f}%')
        avg_edge = sum(b.edge_percent for b in settled) / len(settled)
        avg_odds = sum(b.book_odds for b in settled) / len(settled)
        print(f'Average Edge: {avg_edge:.1f}%')
        print(f'Average Odds: {avg_odds:.2f}')
    print(f'Total Staked: ${staked:.2f}')
    print(f'Total Profit: ${profit:.2f}')
    if staked > 0:
        print(f'ROI: {(profit/staked)*100:.1f}%')


if __name__ == '__main__':
    asyncio.run(main())
