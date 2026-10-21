"""Versioned, atomic JSON snapshots; never deserialize executable objects."""
from collections import deque
from copy import deepcopy
from dataclasses import asdict, fields
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from .simulation import World, Crop, Monster, Villager, CAST, GATES, GATE_MAX, LIMIT

VERSION = 1
DEFAULT_SAVE_PATH = Path(__file__).resolve().parents[1] / "saves" / "village.json"


def jsonable(value):
    if isinstance(value, dict):
        return {key: jsonable(item) for key,item in value.items()}
    if isinstance(value, (tuple,list,deque)):
        return [jsonable(item) for item in value]
    return value


def number(value, low=0, high=1e12):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Invalid saved number: {value!r}")
    return value


def point(value):
    if not isinstance(value,list) or len(value) != 2:
        raise ValueError("Invalid saved position")
    return tuple(number(n,-LIMIT,LIMIT) for n in value)


def strings(value, maximum=8, length=2000):
    if not isinstance(value,list) or len(value)>maximum or any(not isinstance(v,str) or len(v)>length for v in value):
        raise ValueError("Invalid saved memory/text")
    return value


def validate_campaign(value):
    if not isinstance(value,dict) or set(value) != {"attempt","failures","lessons"}:
        raise ValueError("Invalid campaign")
    number(value["attempt"],1,1e9)
    if not isinstance(value['attempt'],int) or not isinstance(value['failures'],list) or len(value['failures']) > 20:
        raise ValueError("Invalid attempt history")
    if not isinstance(value['lessons'],dict) or set(value['lessons']) - {c[0] for c in CAST}:
        raise ValueError("Unknown villager lessons")
    for lessons in value['lessons'].values():
        strings(lessons)
    # Failure records are descriptive JSON, never executable configuration.
    if any(not isinstance(record,dict) for record in value['failures']):
        raise ValueError("Invalid failure records")
    return deepcopy(value)


def snapshot(world):
    return jsonable({"version":VERSION, "campaign":world.campaign, "world":{
        "time":world.time, "villagers":[asdict(bot) for bot in world.villagers],
        "crops":[asdict(crop) for crop in world.crops],
        "monsters":[asdict(monster) for monster in world.monsters],
        "resources":world.resources, "regen_at":world.regen_at, "store":world.store,
        "gates":world.gates, "village_health":world.village_health, "wave":world.wave,
        "next_wave":world.next_wave, "next_monster_id":world.next_monster_id,
        "failed":world.failed, "failure_reason":world.failure_reason,
        "events":list(world.events), "rng_state":world.rng.getstate()}})


def restore(data):
    if not isinstance(data,dict) or data.get('version') != VERSION:
        raise ValueError("Unsupported save format version")
    campaign = validate_campaign(data['campaign'])
    state = data['world']
    world = World(campaign=campaign)
    for name in ('time','regen_at','next_wave'):
        setattr(world,name,number(state[name]))
    for name in ('wave','next_monster_id'):
        value = number(state[name],0 if name=='wave' else 1,1e9)
        if not isinstance(value,int):
            raise ValueError("Invalid integer counter")
        setattr(world,name,value)
    for name,keys,maximum in (('store',{'food','wood'},1e9),('resources',{'orchard'},24),('gates',set(GATES),GATE_MAX)):
        values = state[name]
        if not isinstance(values,dict) or set(values) != keys:
            raise ValueError(f"Invalid saved {name}")
        setattr(world,name,{key:number(value,0,maximum) for key,value in values.items()})
        if name != 'gates' and any(not isinstance(v,int) for v in values.values()):
            raise ValueError('Resource quantities must be integers')
    world.village_health = number(state['village_health'],0,200)
    if not isinstance(state['failed'],bool) or not isinstance(state['failure_reason'],str):
        raise ValueError('Invalid failure state')
    world.failed,world.failure_reason = state['failed'],state['failure_reason'][:2000]
    if len(state['villagers']) != len(CAST):
        raise ValueError('Villager roster changed')
    for bot,saved,profile in zip(world.villagers,state['villagers'],CAST):
        if not isinstance(saved,dict) or set(saved) != {f.name for f in fields(Villager)}:
            raise ValueError('Invalid villager fields')
        if saved['name'] != profile[0] or saved['role'] != profile[1]:
            raise ValueError('Invalid villager identity')
        bot.position = point(saved['position'])
        if not isinstance(saved['path'],list) or len(saved['path']) > 500:
            raise ValueError('Invalid path')
        bot.path = [point(p) for p in saved['path']]
        for name in ('energy','health','hunger'):
            setattr(bot,name,number(saved[name],0,100))
        for name in ('supplies','wood','revision'):
            value=number(saved[name],0,1e9)
            if not isinstance(value,int):
                raise ValueError('Invalid villager counter')
            setattr(bot,name,value)
        for name in ('speech_until','next_think','work_at','attack_at','rally_at'):
            setattr(bot,name,number(saved[name]))
        for name,maximum in (('action',80),('speech',180)):
            value=saved[name]
            if not isinstance(value,str) or len(value)>maximum:
                raise ValueError('Invalid villager text')
            setattr(bot,name,value)
        bot.memory = deque(strings(saved['memory']),maxlen=8)
        bot.lessons = deque(strings(saved['lessons']),maxlen=8)
        if not isinstance(saved['contributions'],dict) or set(saved['contributions']) != set(bot.contributions):
            raise ValueError('Invalid contribution counters')
        for key,value in saved['contributions'].items():
            number(value,0,1e9)
            if not isinstance(value,int):
                raise ValueError('Invalid contribution count')
        bot.contributions = saved['contributions'].copy()
        bot.revision += 1
        # Player possession is a session choice; resume this villager under AI.
        if bot.action == 'player':
            bot.action = 'idle'
        bot.next_think = world.time
    if not isinstance(state['crops'],list) or len(state['crops']) != 4:
        raise ValueError('Invalid crop plots')
    world.crops=[]
    for crop in state['crops']:
        if crop['stage'] not in ('empty','growing','ripe'):
            raise ValueError('Invalid crop stage')
        world.crops.append(Crop(point(crop['position']),crop['stage'],number(crop['age'],0,45)))
    if not isinstance(state['monsters'],list) or len(state['monsters'])>10:
        raise ValueError('Invalid monster list')
    world.monsters=[]
    ids=set()
    for monster in state['monsters']:
        identity=monster['id']
        if not isinstance(identity,str) or len(identity)>50 or identity in ids or monster['gate'] not in GATES:
            raise ValueError('Invalid monster identity')
        ids.add(identity)
        world.monsters.append(Monster(identity,monster['gate'],point(monster['position']),number(monster['health'],0,40)))
    world.events=deque(strings(state['events'],7,2000),maxlen=7)
    def tuples(value):
        return tuple(tuples(v) for v in value) if isinstance(value,list) else value
    world.rng.setstate(tuples(state['rng_state']))
    world.controlled=None
    return world


class SaveStore:
    def __init__(self, path):
        self.path=Path(path).expanduser().resolve()
        self.recovered=False

    def load(self):
        if not self.path.exists():
            return None
        errors=[]
        for candidate in (self.path,self.path.with_suffix(self.path.suffix+'.bak')):
            try:
                if candidate.stat().st_size > 5_000_000:
                    raise ValueError('Save exceeded 5 MB size limit')
                data=json.loads(candidate.read_text(encoding='utf-8'))
                world=restore(data)
                self.recovered=candidate != self.path
                if self.recovered:
                    print(f'Recovered previous snapshot from {candidate}; damaged primary retained until next save.',flush=True)
                return world
            except (OSError,ValueError,KeyError,TypeError,OverflowError,AttributeError) as exc:
                errors.append(f'{candidate.name}: {exc}')
        raise ValueError('Cannot load save. No files were overwritten. '+ '; '.join(errors))

    def save(self, world):
        data=json.dumps(snapshot(world),ensure_ascii=False,indent=2,allow_nan=False)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=self.path.parent,
                                             prefix=self.path.name+'.',suffix='.tmp',delete=False) as handle:
                temporary=Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.exists() and not self.recovered:
                shutil.copy2(self.path,self.path.with_suffix(self.path.suffix+'.bak'))
            os.replace(temporary,self.path)
            self.recovered=False
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def new_attempt(self):
        previous=self.load()
        if previous is None:
            return World()
        campaign=deepcopy(previous.campaign)
        campaign['attempt'] += 1
        # Archiving before replacement preserves the old run even on an early restart.
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        archive=self.path.with_name(self.path.stem+'.'+stamp+self.path.suffix)
        source = self.path.with_suffix(self.path.suffix+'.bak') if self.recovered else self.path
        shutil.copy2(source,archive)
        return World(campaign=campaign)
