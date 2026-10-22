import threading
import unittest
from unittest.mock import patch
from village.brains import BrainScheduler, decision_schema
from village.simulation import World, LOCATIONS, distance


def advance(world, brains, seconds):
    for _ in range(round(seconds*10)):
        world.tick(.1)
        brains.tick()


class AutonomyTests(unittest.TestCase):
    def test_all_six_move_while_single_model_request_is_blocked(self):
        world=World()
        starts=[bot.position for bot in world.villagers]
        entered,release=threading.Event(),threading.Event()
        def slow_request(*args,**kwargs):
            entered.set()
            release.wait(5)
            return {'status':'ok','decision':{'action':'move','target':'farm','dialogue':''}}
        with patch('village.brains.bounded_decision',side_effect=slow_request) as request:
            brains=BrainScheduler(world,'http://localhost:11434','test-model')
            try:
                brains.tick()
                self.assertTrue(entered.wait(2))
                advance(world,brains,2)
                self.assertTrue(brains.busy)
                self.assertEqual(request.call_count,1)
                self.assertEqual(brains.model_decisions,0)
                self.assertEqual(brains.model_history,[])
                self.assertGreaterEqual(brains.local_decisions,6)
                self.assertTrue(all(distance(start,bot.position)>.5
                                    for start,bot in zip(starts,world.villagers)))
            finally:
                release.set()
                brains.results.get(timeout=2)

    def test_local_routines_do_not_control_possessed_villager(self):
        world=World(); world.possess(0)
        starts=[bot.position for bot in world.villagers]
        brains=BrainScheduler(world,'','',demo=True)
        advance(world,brains,2)
        self.assertEqual(world.villagers[0].position,starts[0])
        self.assertEqual(world.villagers[0].action,'player')
        self.assertTrue(all(distance(start,bot.position)>.5
                            for start,bot in zip(starts[1:],world.villagers[1:])))

    def test_error_cooldown_does_not_pause_any_villager(self):
        world=World(); starts=[bot.position for bot in world.villagers]
        brains=BrainScheduler(world,'','',demo=True)
        brains.demo=False
        brains.results.put((0,0,0,None,'connection refused'))
        advance(world,brains,2)
        self.assertIn('FALLBACK',brains.status)
        self.assertTrue(all(distance(start,bot.position)>.5
                            for start,bot in zip(starts,world.villagers)))
        self.assertEqual(brains.model_decisions,0)

    def test_model_destination_is_respected_until_urgent_needs_override_it(self):
        world=World(); bot=world.villagers[0]
        brains=BrainScheduler(world,'','',demo=True)
        brains.results.put((0,bot.revision,world.time,{'action':'move','target':'tavern'},None))
        brains.tick()
        advance(world,brains,2)
        self.assertEqual(bot.action,'walking to tavern')
        self.assertEqual(brains.model_decisions,1)
        self.assertEqual(len(brains.model_history),1)
        bot.hunger=85
        advance(world,brains,1)
        self.assertEqual(bot.action,'walking to storehouse')

    def test_guards_patrol_without_model_requests(self):
        world=World(); soldier=world.villagers[3]
        soldier.position=LOCATIONS['north_gate']
        brains=BrainScheduler(world,'','',demo=True)
        world.apply(soldier,{'action':'guard','target':'north_gate'})
        positions=[]
        for _ in range(70):
            world.tick(.1); brains.tick(); positions.append(soldier.position)
        self.assertEqual(soldier.action,'guarding north_gate')
        self.assertGreater(max(distance(LOCATIONS['north_gate'],p) for p in positions),1)
        self.assertTrue(all(abs(p[0])<=2.5 and 19<=p[1]<=22.5 for p in positions))

    def test_background_plans_avoid_stale_micro_actions(self):
        world=World(); bot=world.villagers[0]; bot.position=LOCATIONS['farm']
        world.villagers[2].position=(-13,9)
        observation=world.observe(bot)
        self.assertIn('harvest',observation['available_actions'])
        observation['decision_layer']='strategic'
        actions={branch['properties']['action']['enum'][0] for branch in decision_schema(observation)['oneOf']}
        self.assertEqual(actions,{'move','guard','talk'})

    def test_farm_workers_have_distinct_work_slots(self):
        world=World()
        destinations=[]
        for index in (0,2,5):
            bot=world.villagers[index]
            self.assertTrue(world.apply(bot,{'action':'move','target':'farm'}))
            destinations.append(bot.path[-1])
        self.assertEqual(len(set(destinations)),3)

    def test_farmers_check_the_fields_while_crops_are_growing(self):
        world=World(); farmer=world.villagers[0]
        farmer.position=LOCATIONS['farm']
        for crop in world.crops:
            crop.stage='growing'; crop.age=0
        brains=BrainScheduler(world,'','',demo=True)
        brains.tick()
        self.assertEqual(farmer.action,'checking crops')
        self.assertTrue(farmer.path)
        before=farmer.position
        advance(world,brains,1)
        self.assertNotEqual(farmer.position,before)

    def test_routine_chatter_preserves_work_and_stays_out_of_model_history(self):
        world=World(); brains=BrainScheduler(world,'','',demo=True)
        bot=world.villagers[0]
        world.apply(bot,{'action':'move','target':'farm'})
        before=list(bot.path)
        world.time=5
        brains._social()
        self.assertEqual(bot.path,before)
        self.assertTrue(any(b.speech for b in world.villagers))
        self.assertEqual(brains.model_history,[])
        self.assertEqual(brains.model_decisions,0)


if __name__=='__main__':
    unittest.main()
