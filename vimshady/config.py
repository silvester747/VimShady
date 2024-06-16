import platformdirs
import toml

from dataclasses import asdict, dataclass
from pathlib import Path

app_name = "VimShady"
app_author = "Silvester747"
user_data_dir = Path(platformdirs.user_data_dir(app_name, app_author))
config_file = user_data_dir / "config.toml"


@dataclass
class Config(object):
    window_x: int = 0
    window_y: int = 0
    window_width: int = 640
    window_height: int = 480

    def save(self):
        if not user_data_dir.exists():
            user_data_dir.mkdir(parents=True, exist_ok=False)
        with config_file.open("w") as f:
            toml.dump(asdict(self), f)

    @classmethod
    def load(cls):
        if config_file.is_file():
            return cls(**toml.load(config_file))
        else:
            return cls()
