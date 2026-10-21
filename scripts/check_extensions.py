"""Render a temporary custom model and exercise configured plugin input/save hooks.

Uses Panda3D messenger dispatch, not OS keyboard events or human playtesting.
"""

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=artifacts) as directory:
        folder = Path(directory)
        (folder / "prop.egg").write_text("""<CoordinateSystem> { Z-up }
<VertexPool> v {
 <Vertex> 0 { 0 0 0 } <Vertex> 1 { 2 0 0 } <Vertex> 2 { 0 0 2 }
}
<Polygon> { <RGBA> { 0.9 0.2 0.2 1 } <VertexRef> { 0 1 2 <Ref> { v } } }
""")
        catalog = json.loads((ROOT / "village/data/assets/catalog.json").read_text())
        catalog["prefabs"]["custom_prop"] = {
            "parts": [
                {
                    "name": "custom_model",
                    "model": "prop.egg",
                    "position": [0, 0, 0],
                    "scale": [1, 1, 1],
                    "color": [1, 1, 1],
                }
            ]
        }
        catalog["instances"].append({"prefab": "custom_prop", "position": [6, 7, 0]})
        manifest = folder / "catalog.json"
        manifest.write_text(json.dumps(catalog))
        config = json.loads((ROOT / "examples/custom.json").read_text())
        config["assets"] = {"manifest": "catalog.json"}
        config["controls"]["actions"]["encourage"] = "y"
        config_path = folder / "custom.json"
        config_path.write_text(json.dumps(config))
        from village.config import configure

        configure(config_path)
        from village.game import VillageGame
        from village.persistence import SaveStore

        game = VillageGame(
            SimpleNamespace(
                smoke_test=True, demo=True, url="", model="", no_save=True, pace=0.5
            )
        )
        try:
            assert not game.render.find("**/custom_prop").isEmpty()
            game.takeover(0)
            bot, other = game.world.villagers[:2]
            other.energy = 50
            game.messenger.send("y")
            assert other.energy == 53 and bot.energy == 98
            assert game.world.extension_state["encourage"][bot.name] == 10
            assert "b harvest" in game.controls.getText().lower()
            save = SaveStore(folder / "save.json")
            save.save(game.world)
            assert save.load().extension_state == game.world.extension_state
            game.graphicsEngine.renderFrame()
            game.graphicsEngine.renderFrame()
            from panda3d.core import Filename

            assert game.win.saveScreenshot(
                Filename.fromOsSpecific(str(artifacts / "extension-check.png"))
            )
            report = {
                "passed": [
                    "external Egg model loaded from manifest-relative path",
                    "configured key dispatched custom action with validated costs and target",
                    "HUD reflects remapped harvest key",
                    "plugin cooldown survived save/reload",
                ],
                "method": "temporary config/manifest, Panda3D messenger, offscreen Windows/Linux render",
            }
            (artifacts / "extension-check.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            print(json.dumps(report, indent=2))
        finally:
            game.destroy()


if __name__ == "__main__":
    main()
