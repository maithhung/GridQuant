import argparse
from pathlib import Path

from gridquant.merit_order import clear_market
from gridquant.merit_order_io import load_merit_order_case


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    case = load_merit_order_case(args.input)

    result = clear_market(
        generators=case.generators,
        demand_mw=case.demand_mw,
        duration_hours=case.duration_hours,
    )

    print(f"Example: {case.name}")
    print(f"Demand: {case.demand_mw} MW")
    print(f"Duration: {case.duration_hours} h")
    print(f"Dispatch: {result.dispatch_mw}")
    print(f"Clearing price: {result.clearing_price_per_mwh} EUR/MWh")
    print(f"Cleared volume: {result.cleared_volume_mw} MW")
    print(f"Delivered energy: {result.cleared_energy_mwh} MWh")
    print(f"Unmet demand: {result.unmet_demand_mw} MW")
    print(f"Profit: {result.operating_profit_eur}")


if __name__ == "__main__":
    main()