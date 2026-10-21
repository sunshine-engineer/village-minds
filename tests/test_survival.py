from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from village.simulation import World, Monster, LOCATIONS, GATE_MAX, CROP_GROW_SECONDS
from village.brains import BrainScheduler, decision_schema, request_decision
from village.persistence import SaveStore, snapshot, restore


def advance(world, seconds, brains=None):
    for _ in range(round(seconds*10)):
        world.tick(.1)
        if brains:
            brains.tick()


class SurvivalTests(unittest.TestCase):
    def test_plant_growth_harvest_deposit_and_eating(self):
        world=World()
        farmer=world.villagers[0]
        farmer.position=LOCATIONS['farm']
        for crop in world.crops:
            crop.stage='empty'; crop.age=0
        self.assertFalse(world.apply(farmer,{'action':'harvest'}))
        self.assertTrue(world.apply(farmer,{'action':'farm'}))
        advance(world,CROP_GROW_SECONDS-1)
        self.assertFalse(world.apply(farmer,{'action':'harvest'}))
        advance(world,2)
        self.assertTrue(world.apply(farmer,{'action':'harvest'}))
        self.assertEqual(farmer.supplies,6)
        shared=world.store['food']
        self.assertFalse(world.apply(farmer,{'action':'deposit'}))
        advance(world,1.1)
        farmer.position=LOCATIONS['storehouse']
        self.assertTrue(world.apply(farmer,{'action':'deposit'}))
        self.assertEqual(world.store['food'],shared+6)
        self.assertEqual(farmer.supplies,0)
        farmer.hunger=60
        advance(world,1.1)
        self.assertTrue(world.apply(farmer,{'action':'eat'}))
        self.assertLess(farmer.hunger,30)
        self.assertEqual(world.store['food'],shared+5)

    def test_worker_repairs_need_shared_wood_and_distance(self):
        world=World(); worker=world.villagers[1]
        world.gates['north_gate']=50
        self.assertFalse(world.apply(worker,{'action':'repair','target':'north_gate'}))
        worker.position=LOCATIONS['north_gate']; world.store['wood']=0
        self.assertFalse(world.apply(worker,{'action':'repair','target':'north_gate'}))
        world.store['wood']=1
        self.assertTrue(world.apply(worker,{'action':'repair','target':'north_gate'}))
        self.assertEqual(world.gates['north_gate'],68)
        self.assertEqual(world.store['wood'],0)
        self.assertFalse(world.apply(worker,{'action':'repair','target':'north_gate'}))

    def test_guard_defeats_monster_and_later_waves_respawn(self):
        world=World(); soldier=world.villagers[3]
        soldier.position=LOCATIONS['north_gate']
        world.monsters=[Monster('test','north_gate',(0,26))]
        self.assertTrue(world.apply(soldier,{'action':'guard','target':'north_gate'}))
        advance(world,3)
        self.assertEqual(world.monsters,[])
        self.assertEqual(soldier.contributions['kills'],1)
        world.next_wave=world.time
        advance(world,.1)
        self.assertTrue(world.monsters)
        self.assertTrue(all(max(abs(x) for x in m.position)>24 for m in world.monsters))
        self.assertEqual(world.wave,1)

    def test_soldiers_have_combat_bonus_and_cooldown(self):
        world=World(); soldier=world.villagers[3]
        soldier.position=(0,21)
        world.monsters=[Monster('test','north_gate',(0,26))]
        self.assertTrue(world.apply(soldier,{'action':'attack','target':'test'}))
        self.assertEqual(world.monsters[0].health,20)
        self.assertFalse(world.apply(soldier,{'action':'attack','target':'test'}))
        self.assertFalse(world.apply(soldier,{'action':'attack','target':'unknown'}))

    def test_manual_movement_cancels_previous_guard_route(self):
        world=World(); world.possess(3); bot=world.villagers[3]
        world.apply(bot,{'action':'guard','target':'north_gate'})
        self.assertTrue(bot.path)
        before=sum((a-b)**2 for a,b in zip(bot.position,LOCATIONS['north_gate']))
        advance(world,1)
        self.assertLess(sum((a-b)**2 for a,b in zip(bot.position,LOCATIONS['north_gate'])),before)
        world.move_player(1,0,.1)
        self.assertEqual(bot.path,[])
        self.assertEqual(bot.action,'player')

    def test_starvation_death_and_dead_villager_rejection(self):
        world=World(); bot=world.villagers[0]
        bot.health=.01; bot.hunger=99
        advance(world,.1)
        self.assertFalse(bot.alive)
        self.assertEqual(bot.action,'fallen')
        self.assertFalse(world.apply(bot,{'action':'rest'}))
        world.possess(0)
        self.assertIsNone(world.controlled)
        self.assertNotIn(bot.name,world.observe(world.villagers[1])['conversation_partners'])

    def test_idle_village_fails_but_cooperative_baseline_survives(self):
        idle=World(); cooperative=World()
        brains=BrainScheduler(cooperative,'','',demo=True)
        advance(idle,900)
        advance(cooperative,900,brains)
        self.assertTrue(idle.failed)
        self.assertFalse(cooperative.failed)
        self.assertEqual(cooperative.village_health,200)
        self.assertGreater(sum(v.contributions['deposited_food'] for v in cooperative.villagers),0)
        self.assertGreater(sum(v.contributions['kills'] for v in cooperative.villagers),0)
        self.assertGreater(sum(v.contributions['repairs'] for v in cooperative.villagers),0)
        self.assertEqual(len(idle.campaign['failures']),1)
        advance(idle,10)
        self.assertEqual(len(idle.campaign['failures']),1)

    def test_contextual_schema_exposes_survival_actions(self):
        world=World(); bot=world.villagers[0]
        bot.position=LOCATIONS['farm']
        observation=world.observe(bot)
        schema=decision_schema(observation)
        choices={branch['properties']['action']['enum'][0] for branch in schema['oneOf']}
        self.assertIn('harvest',choices)
        self.assertNotIn('repair',choices)
        self.assertIn('guard',choices)
        self.assertIn('storehouse',observation['village_map'])
        self.assertIn('storehouse',observation['village'])


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'village.json'
        self.store=SaveStore(self.path)
    def tearDown(self):
        self.temp.cleanup()

    def test_roundtrip_preserves_world_timers_inventory_memories_and_rng(self):
        world=World(); bot=world.villagers[0]
        bot.position=LOCATIONS['farm']
        world.apply(bot,{'action':'harvest'})
        advance(world,2)
        world.apply(bot,{'action':'farm'})
        world.apply(bot,{'action':'move','target':'storehouse'})
        world.say(bot,'We must cooperate or the village will fall.')
        world.spawn_wave()
        advance(world,7)
        world.gates['east_gate']=73
        bot.lessons.append('Share food instead of hoarding it.')
        self.store.save(world)
        loaded=self.store.load()
        before=snapshot(world); after=snapshot(loaded)
        for b,a in zip(before['world']['villagers'],after['world']['villagers']):
            b['revision']=a['revision']; b['next_think']=a['next_think']
        self.assertEqual(before,after)
        self.assertEqual(loaded.rng.random(),world.rng.random())
        # Loading neither grows crops nor advances monsters while offline.
        self.assertEqual(loaded.time,world.time)
        self.assertEqual(loaded.crops[0].age,world.crops[0].age)

    def test_failure_history_survives_new_attempt_and_enters_model_context(self):
        world=World(); world.gates['north_gate']=0; world.store['food']=0
        world.fail('No one defended the north gate.')
        self.store.save(world)
        loaded=self.store.load()
        self.assertTrue(loaded.failed)
        self.assertEqual(len(loaded.campaign['failures']),1)
        fresh=self.store.new_attempt()
        self.store.save(fresh)
        resumed=self.store.load()
        self.assertFalse(resumed.failed)
        self.assertEqual(resumed.campaign['attempt'],2)
        self.assertEqual(resumed.village_health,200)
        self.assertTrue(list(self.path.parent.glob('village.*Z.json')))
        observation=resumed.observe(resumed.villagers[0])
        self.assertIn('north gate',observation['lessons_from_previous_failures'][-1])
        class Response:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,limit): return b'{"message":{"content":"{\\"action\\":\\"rest\\",\\"target\\":\\"\\",\\"dialogue\\":\\"\\"}"}}'
        with patch('urllib.request.urlopen',return_value=Response()) as send:
            request_decision('http://localhost:11434','test',observation)
        payload=json.loads(send.call_args.args[0].data)
        self.assertIn('No one defended the north gate',payload['messages'][1]['content'])

    def test_corrupt_primary_recovers_previous_valid_snapshot(self):
        world=World(); self.store.save(world)
        world.store['food']=99; self.store.save(world)
        self.path.write_text('{partial')
        recovered=self.store.load()
        self.assertTrue(self.store.recovered)
        self.assertEqual(recovered.store['food'],18)
        self.store.save(recovered)
        self.assertEqual(self.store.load().store['food'],18)

    def test_bad_save_without_backup_is_not_overwritten(self):
        bad='{"version":99}'
        self.path.write_text(bad)
        with self.assertRaises(ValueError): self.store.load()
        self.assertEqual(self.path.read_text(),bad)

    def test_failed_atomic_replace_preserves_existing_save(self):
        world=World(); self.store.save(world)
        old=self.path.read_bytes()
        world.store['food']=22
        with patch('village.persistence.os.replace',side_effect=OSError('disk error')):
            with self.assertRaises(OSError): self.store.save(world)
        self.assertEqual(self.path.read_bytes(),old)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_save_immediately_after_killing_blow_before_entity_cleanup(self):
        world=World(); bot=world.villagers[0]; bot.position=(0,21)
        world.monsters=[Monster('weak','north_gate',(0,26),health=5)]
        self.assertTrue(world.apply(bot,{'action':'attack','target':'weak'}))
        self.store.save(world)
        loaded=self.store.load()
        self.assertEqual(loaded.monsters[0].health,0)
        advance(loaded,.1)
        self.assertEqual(loaded.monsters,[])

    def test_invalid_nonfinite_state_and_monster_counts_rejected(self):
        data=snapshot(World())
        data['world']['villagers'][0]['health']=float('nan')
        with self.assertRaises(ValueError): restore(data)
        data=snapshot(World()); data['world']['monsters']=[{}]*11
        with self.assertRaises(ValueError): restore(data)


if __name__=='__main__':
    unittest.main()
