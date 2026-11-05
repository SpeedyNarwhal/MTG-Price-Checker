from mtg_price_checker.paths import frontend_dist_dir, project_root


def test_project_root_points_at_repo() -> None:
    root = project_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "mtg_price_checker").is_dir()


def test_frontend_dist_dir_is_under_project_root() -> None:
    assert frontend_dist_dir() == project_root() / "web" / "frontend" / "dist"
