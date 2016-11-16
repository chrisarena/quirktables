#!/usr/bin/env python3

import requests

from collections import defaultdict
from enum import Enum

html_template = '''
<!DOCTYPE html>
<html>
<head>
    <title>%s Mech QuirkTable</title>
    <link rel="stylesheet" type="text/css" href="style.css">
</head>
<body>
    %s
</body>
</html>
'''

smurfys_url = 'http://mwo.smurfy-net.de/api/data/'
file_type = '.json'

smurfys_endpoints = {}
for endpoint in ('mechs', 'omnipods', 'prices', 'modules', 'weapons', 'ammo', 'ID'):
    smurfys_endpoints[endpoint] = '%s%s%s' % (smurfys_url, endpoint, file_type)

class Component(Enum):
    hd = 'head'
    ra = 'right_arm'
    rt = 'right_torso'
    ct = 'centre_torso'
    lt = 'left_torso'
    la = 'left_arm'
    rl = 'right_leg'
    ll = 'left_leg'

    def __str__(self):
        if self.value == 'centre_torso':
            return 'Center Torso'
        else:
            return self.value.replace('_', ' ').title()


class Quirk(object):
    def __init__(self, quirk_json):
        self.name = quirk_json['translated_name']
        self.value = quirk_json['value']
        non_percent_quirks = ('ADDITIONAL', 'BONUS', 'HARDPOINT', 'ANGLE', 'JUMP', 'NARC', 'SENSOR')
        if not any(item in self.name for item in non_percent_quirks):
            self.value = str(int(float(self.value) * 100)) + '%'

    def __repr__(self):
        return '(%s) %s: %s' % (self.__class__.__name__, self.name, self.value)

    def __lt__(self, other):
        return self.name < other.name # allows sorting

    def __eq__(self, other):
        return self.name == other.name and self.value == other.value

    def __hash__(self):
        return hash((self.name, self.value))


class Omnipod(object):
    def __init__(self, pod_dict):
        self.component = Component(pod_dict['configuration']['name'])
        self.variant = pod_dict['details']['set']
        self.quirks = self._get_quirks(pod_dict)
        self.hardpoints = self._get_hardpoints(pod_dict)
        self._add_hardpoints_to_quirks()

    @staticmethod
    def _get_hardpoints(pod_dict):
        hardpoints = {'beam': 0, 'missle': 0, 'ballistic': 0, 'ams': 0, 'ecm': 0}
        for omnipod in pod_dict.values():
            for hardpoint in omnipod.get('hardpoints', []):
                hardpoints[hardpoint['type'].lower()] += int(hardpoint['count'])
        return hardpoints

    def _add_hardpoints_to_quirks(self):
        if all(count == 0 for count in self.hardpoints.values()):
            return # No hardpoints

        class Hardpoint(object):
            def __init__(self, shortname, color):
                self.shortname = shortname
                self.color = color
                self.count = 0

        hp_objects = {
            'beam': Hardpoint('E', 'orange'),
            'missle': Hardpoint('M', 'teal'),
            'ballistic': Hardpoint('B', 'purple'),
            'ams': Hardpoint('AMS', 'red'),
            'ecm': Hardpoint('ECM', 'green'),
        }

        hardpoints = []
        for hardpoint, count in self.hardpoints.items():
            if count > 0:
                hp_object = hp_objects[hardpoint]
                hp_object.count = count
                hardpoints.append(hp_object)

        hardpoint_string = ', '.join('<font color="%s">%s%s</font>'
                                     % (hp.color, hp.count, hp.shortname) for hp in hardpoints)
        quirk = {'translated_name': '\n\t<b>HARDPOINTS</b>', 'value': hardpoint_string}
        self.quirks.append(Quirk(quirk))

    @staticmethod
    def _get_quirks(pod_dict):
        quirks = [Quirk(quirk) for quirk in pod_dict['configuration']['quirks']]
        quirks.sort()
        return quirks

    def __str__(self):
        return '%s: %s' % (self.variant, self.component)

class Mech(object):
    name = None

    def __repr__(self):
        return '%s: %s' % (self.__class__.__name__, self.name)

    def __lt__(self, other):
        return self.name < other.name  # allows sorting

    @staticmethod
    def _quirks_string(quirks):
        return ('\n'.join('%s: %s' % (quirk.name, quirk.value) for quirk in quirks)
                if quirks else '--')

    def _convert_quirks_to_strings(self, matrix):
        # Convert list of Quirk objects into strings for display as we're done filtering
        string_matrix = []
        for row in matrix:
            new_row = []
            for cell in row:
                if isinstance(cell, Omnipod):
                    text = self._quirks_string(cell.quirks)
                elif isinstance(cell, list):
                    text = self._quirks_string(cell)
                elif isinstance(cell, str):
                    text = cell
                else:
                    print(cell)
                    raise Exception('Type of cell is %s' % type(cell))
                new_row.append(text)
            string_matrix.append(new_row)
        return string_matrix


class Battlemech(Mech):
    def __init__(self, name, chassis_json):
        self.name = name.upper()
        self.quirk_dict = {variant['translated_name']: variant['details']['quirks']
                           for variant in chassis_json}
        for variant, quirk_list in self.quirk_dict.items():
            self.quirk_dict[variant] = sorted([Quirk(quirk) for quirk in quirk_list])
        self.matrix = self._build_matrix()

    def _build_matrix(self):
        shared_quirks = []
        # if it's a shared quirk, add it to the shared list and remove it elsewhere
        for quirk in [item for sublist in self.quirk_dict.values() for item in sublist]:
            if all(quirk in self.quirk_dict[variant] for variant in self.quirk_dict.keys()):
                shared_quirks.append(quirk)
                for variant in self.quirk_dict.keys():
                    self.quirk_dict[variant].remove(quirk)

            # TODO: Add hardpoints quirk for each variant
        matrix = []
        for variant, variant_quirks in sorted(self.quirk_dict.items()):
            variant_row = [variant] + [variant_quirks]
            matrix.append(variant_row)
        shared_row = ['<b>SHARED</b>'] + [shared_quirks]
        matrix.append(shared_row)
        string_matrix = self._convert_quirks_to_strings(matrix)
        header_row = [self.name] + ['Quirks']
        string_matrix.insert(0, header_row)
        return string_matrix


class Omnimech(Mech):
    def __init__(self, mech_tuple):
        self.name, pod_dict = mech_tuple[0].upper(), mech_tuple[1]
        self.omnipods = [Omnipod(pod) for pod in pod_dict.values()]
        self.variants = set(omnipod.variant for omnipod in self.omnipods)
        self.matrix = self._build_matrix()

    def _find_pod(self, variant, component):
        return next(pod for pod in self.omnipods
                    if variant == pod.variant and component is pod.component)

    def _build_matrix(self):
        matrix = []
        for variant in sorted(self.variants):
            pod_quirks = [self._find_pod(variant, component) for component in Component]
            variant_row = [variant] + pod_quirks
            matrix.append(variant_row)

        # Build a row containing quirks shared by all variants for that component
        shared_row = ['<b>SHARED</b>']
        components = list(zip(*matrix))[1:] # ignore variant names
        for component in components:
            component_quirks = set()
            for pod in component:
                for quirk in pod.quirks:
                    if 'HARDPOINTS' in quirk.name:
                        continue # Skip this special case, it has html embedded
                    component_quirks.add(quirk)

            # Quirks shared by each omnipod for this component
            shared_component_quirks = []
            for quirk in component_quirks:
                if all(quirk in pod.quirks for pod in component):
                    shared_component_quirks.append(quirk)
            shared_row.append(sorted(shared_component_quirks))

            # Overwrite each pod's quirks with what is non-shared
            for pod in component:
                new_quirks = [quirk for quirk in pod.quirks
                              if quirk not in shared_component_quirks]
                pod.quirks = new_quirks
        matrix.append(shared_row)

        string_matrix = self._convert_quirks_to_strings(matrix)
        header_row = [self.name] + [str(component) for component in Component]
        string_matrix.insert(0, header_row)
        return string_matrix


def get_mech_list():
    """
    Get latest .json mech data from smurfys API
    :return: list of BattleMech and OmniMech based on results.
    """
    r = requests.get(smurfys_endpoints['mechs'])
    mech_json_list = list(r.json().values()) # drop useless id keying
    battlemech_indicators = ['iic', 'kodiak', 'spirit bear']
    omnimech_list = []
    battlemech_list = []
    for mech_json in mech_json_list:
        name = mech_json['translated_name'].lower()
        if '(c)' in name:
            continue # Champion mech; a duplicate
        if (mech_json['faction'] == 'Clan' and
                not any(indicator in name for indicator in battlemech_indicators)):
            omnimech_list.append(mech_json)
        else:
            battlemech_list.append(mech_json)
    return battlemech_list, omnimech_list

def get_omnipod_dict():
    """
    :return: mapping of variant: {omnipod_id: {data}}
    """
    return requests.get(smurfys_endpoints['omnipods']).json()

def create_html_table(list_of_lists):
    table_string = '<table class="csstable">'
    for sublist in list_of_lists:
        table_string += '    <tr><td>'
        table_string += '        </td><td>'.join(sublist)
        table_string += '    </td></tr>'
    table_string += '</table>'
    return table_string

def create_omnimech_tables():
    all_omnipods = get_omnipod_dict()  # map of {chassis: all omnipods for that chassis,}
    omnimechs = [Omnimech(mech_tuple) for mech_tuple in all_omnipods.items()]
    for mech in sorted(omnimechs):
        print(mech)
        with open('tables/%s.html' % mech.name.lower(), 'w') as f:
            html_table = create_html_table(mech.matrix)
            f.write(html_template % (mech.name, html_table))
    return len(omnimechs)

def create_battlemech_tables():
    battlemechs, _ = get_mech_list()
    chassises = defaultdict(list)
    for mech in battlemechs:
        chassises[mech['family']].append(mech)
    battlemechs = [Battlemech(name, mechs) for name, mechs in chassises.items()]
    for mech in sorted(battlemechs):
        print(mech)
        with open('tables/%s.html' % mech.name.lower(), 'w') as f:
            html_table = create_html_table(mech.matrix)
            f.write(html_template % (mech.name, html_table))
    return len(battlemechs)

if __name__ == '__main__':
    omni_count = create_omnimech_tables()
    battle_count = create_battlemech_tables()
    print('Completed successfully: wrote %s html files' % (omni_count + battle_count))

