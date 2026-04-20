import argparse
from robot_game import run_game


def main() -> None:
    parser = argparse.ArgumentParser(description="Robot Channel Switching Game")
    parser.add_argument("--seed",     type=int,   default=42,  help="RNG seed")
    parser.add_argument("--robots",   type=int,   default=12,  help="Number of robots")
    parser.add_argument("--duration", type=float, default=120, help="Game duration in seconds")
    args = parser.parse_args()
    run_game(seed=args.seed, n_robots=args.robots, duration=args.duration)


if __name__ == "__main__":
    main()
