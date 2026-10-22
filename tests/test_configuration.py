"""Config and plugin checks use subprocesses: settings are startup-only."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from village.config import load_config, DATA, fingerprint
from village.assets import AssetCatalog
from village.persistence import restore, snapshot
from village.simulation import World

ROOT = Path(__file__).resolve().parents[1]


def run(code, config=None):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(config or {}), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from village.config import configure; configure("
                + repr(str(path))
                + ");"
                + code,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout


class ConfigurationTests(unittest.TestCase):
    def test_overrides_merge_without_changing_packaged_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"rules":{"crop_grow_seconds":12}}')
            settings = load_config(path)
            self.assertEqual(settings["rules"]["crop_grow_seconds"], 12)
            self.assertEqual(settings["rules"]["gate_health"], 150)
            self.assertEqual(load_config()["rules"]["crop_grow_seconds"], 45)

    def test_invalid_settings_fail_before_game_import(self):
        invalid = [
            {"rulz": {}},
            {"rules": {"gate_health": -1}},
            {"runtime": {"pace": True}},
            {"runtime": {"pace": 11}},
            {"display": {"window_size": [0, 900]}},
            {"controls": {"forward": "s"}},
            {"ai": {"default_profile": "missing"}},
            {"world": {"cast": []}},
            {"world": {"locations": {"north_gate": [0, 0]}}},
            {"ai": {"profiles": {"broken": {"backend": "ollama"}}}},
            {"ai": {"villager_profiles": {"missing": "local_qwen"}}},
            {"rules": {"wave_growth_every": 1.5}},
            {"evaluation": {"checkpoint_strategy": "unknown"}},
            {"evaluation": {"control": "missing"}},
            {"coordination": {"mode": "missing"}},
            {"coordination": {"priority": ["food"]}},
            {"coordination": {"max_active_tasks": 0}},
            {"coordination": {"role_preferences": {"defend": ["missing"]}}},
            {"evaluation": {"scenario_name": " "}},
            {
                "evaluation": {
                    "controls": {
                        "no-sharing": {"disabled_actions": ["deposit", "deposit"]}
                    }
                }
            },
            {"evaluation": {"controls": {"no-sharing": {"disabled_actions": [7]}}}},
            {"evaluation": {"role_order": []}},
            {"evaluation": {"role_order": ["soldier", "soldier"]}},
            {"evaluation": {"role_order": ["missing"]}},
            {"evaluation": {"checkpoint_start_seconds": -1}},
            {"ai": {"social_messages": {"generic": "{unknown}"}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            for data in invalid:
                with self.subTest(data=data):
                    path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        load_config(path)

    def test_duplicate_and_nonfinite_json_settings_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for content in (
                '{"rules":{"gate_health":100,"gate_health":200}}',
                '{"extension_settings":{"value":NaN}}',
            ):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_legacy_save_rejects_custom_gameplay_without_reset(self):
        run(
            "from village.persistence import restore,snapshot; from village.world import World; "
            "d=snapshot(World()); d['version']=1; d.pop('config_fingerprint'); "
            "exec(\"try:\\n restore(d)\\nexcept ValueError:\\n pass\\nelse:\\n raise AssertionError('legacy settings mismatch accepted')\")",
            {"rules": {"gate_health": 220}},
        )

    def test_relative_paths_resolve_from_override_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            prompt = Path(directory) / "prompt.txt"
            prompt.write_text("You are a villager.")
            path.write_text(
                '{"ai":{"system_prompt":"prompt.txt"},"runtime":{"save_path":"session.json"}}'
            )
            settings = load_config(path)
            self.assertEqual(settings["ai"]["system_prompt"], str(prompt.resolve()))
            self.assertEqual(
                settings["runtime"]["save_path"],
                str((path.parent / "session.json").resolve()),
            )

    def test_balance_settings_affect_actions_and_persistence(self):
        run(
            "from village.world import World; from village.persistence import restore,snapshot; "
            "w=World(); b=w.villagers[0]; b.position=(-14,9); "
            "assert w.apply(b,{'action':'harvest'}); assert b.supplies==9; "
            "assert w.gates['north_gate']==220; assert w.crops[1].age==30; "
            "assert restore(snapshot(w)).villagers[0].supplies==9",
            {
                "rules": {"gate_health": 220, "crop_grow_seconds": 30},
                "roles": {"farmer": {"harvest_yield": 9}},
            },
        )

    def test_custom_roster_more_than_six_uses_repeatable_work_offsets(self):
        cast = deepcopy(load_config()["world"]["cast"])
        cast.append({**cast[0], "name": "June"})
        run(
            "from village.world import World; w=World(); "
            "assert len(w.villagers)==7; assert w.destination(w.villagers[-1],'farm')",
            {
                "world": {"cast": cast},
                "controls": {"takeover_keys": ["1", "2", "3", "4", "5", "6", "7"]},
            },
        )

    def test_legacy_saves_load_under_defaults(self):
        data = snapshot(World())
        data["version"] = 1
        data.pop("config_fingerprint")
        data["world"].pop("extension_state")
        self.assertEqual(restore(data).villagers[0].name, "Mira")

    def test_mismatched_save_config_is_rejected(self):
        data = snapshot(World())
        data["config_fingerprint"] = "different"
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            restore(data)

    def test_visual_model_overrides_preserve_save_fingerprint(self):
        original = load_config()
        changed = deepcopy(original)
        changed["display"]["fov"] = 65
        changed["ai"]["profiles"]["local_qwen"]["model"] = "different"
        self.assertEqual(fingerprint(original), fingerprint(changed))
        changed["rules"]["gate_health"] = 500
        self.assertNotEqual(fingerprint(original), fingerprint(changed))

    def test_asset_manifest_required_parts_and_duplicates(self):
        catalog = AssetCatalog(DATA / "assets/catalog.json")
        self.assertIn("villager", catalog.catalog["prefabs"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            data = deepcopy(catalog.catalog)
            data["prefabs"]["villager"]["parts"].append(
                data["prefabs"]["villager"]["parts"][0]
            )
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                AssetCatalog(path)

    def test_packaged_example_enables_validated_persistent_plugin_action(self):
        config = json.loads((ROOT / "examples/custom.json").read_text())
        run(
            "from village.world import World; from village.persistence import snapshot,restore; "
            "w=World(); a,b=w.villagers[:2]; b.energy=50; "
            "assert 'encourage' in w.available_actions(a); "
            "assert not w.apply(a,{'action':'encourage','target':'missing'}); "
            "assert w.apply(a,{'action':'encourage','target':b.name}); assert b.energy==53; "
            "assert not w.apply(a,{'action':'encourage','target':b.name}); "
            "v=restore(snapshot(w)); assert v.extension_state==w.extension_state",
            config,
        )

    def test_plugin_registration_rejects_builtin_replacement_and_duplicate_system(self):
        from village.extensions import Extensions

        ext = Extensions()
        with self.assertRaises(ValueError):
            ext.register_action(
                "move", available=lambda w, b: [], execute=lambda w, b, d: True
            )
        ext.register_system("clock", lambda w, dt: None)
        with self.assertRaises(ValueError):
            ext.register_system("clock", lambda w, dt: None)

    def test_custom_system_and_policy_are_called(self):
        from village.extensions import Extensions

        ext = Extensions()
        calls = []
        ext.register_system("example", lambda world, dt: calls.append(dt))
        ext.register_policy("farmer", lambda world, bot: {"action": "rest"})
        world = World(extensions=ext)
        world.tick(0.1)
        self.assertEqual(calls, [0.1])
        self.assertEqual(world.fallback(world.villagers[0]), {"action": "rest"})

    def test_per_villager_profile_resolution(self):
        config = json.loads((ROOT / "examples/models.json").read_text())
        run(
            "from village.world import World; from village.brains import BrainScheduler; "
            "b=BrainScheduler(World(),'','',demo=True); "
            "assert b.profile_for('Edda')['backend']=='openai_compatible'; "
            "assert b.profile_for('Mira')['backend']=='ollama'",
            config,
        )


if __name__ == "__main__":
    unittest.main()
