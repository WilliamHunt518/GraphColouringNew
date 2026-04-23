import argparse
from robot_world import COMPLEXITY_PRESETS, SPEED_MIN, SPEED_MAX
from robot_game import run_game


def main() -> None:
    parser = argparse.ArgumentParser(description="Drone Channel Assignment")
    parser.add_argument(
        "--complexity", choices=list(COMPLEXITY_PRESETS), default=None,
        help="Named complexity level: easy / medium / hard",
    )
    parser.add_argument("--seed",     type=int,   default=42,   help="RNG seed")
    parser.add_argument("--duration", type=float, default=90.0, help="Trial duration in seconds")
    parser.add_argument("--epsilon",  type=float, default=0.20, help="Agent noise rate (0=perfect)")
    # Manual overrides (take precedence over --complexity)
    parser.add_argument("--robots",   type=int,   default=None, help="Number of drones")
    parser.add_argument("--v-min",    type=float, default=None, help="Min drone speed (px/s)")
    parser.add_argument("--v-max",    type=float, default=None, help="Max drone speed (px/s)")
    args = parser.parse_args()

    if args.complexity:
        n_default, vmin_default, vmax_default = COMPLEXITY_PRESETS[args.complexity]
        complexity_label = args.complexity
    else:
        n_default, vmin_default, vmax_default = 12, SPEED_MIN, SPEED_MAX
        complexity_label = "custom"

    n_robots = args.robots if args.robots is not None else n_default
    v_min    = args.v_min  if args.v_min  is not None else vmin_default
    v_max    = args.v_max  if args.v_max  is not None else vmax_default

    run_game(
        seed=args.seed,
        n_robots=n_robots,
        duration=args.duration,
        v_min=v_min,
        v_max=v_max,
        epsilon=args.epsilon,
        complexity=complexity_label,
    )


if __name__ == "__main__":
    main()
