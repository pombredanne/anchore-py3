#!/usr/bin/env python

import sys
import os
import re
import anchore.anchore_utils

gate_name = "PKGDIFF"
triggers = {
    'PKGVERSIONDIFF':
    {
        'description':'triggers if the evaluated image has a package installed with a different version of the same package from a previous base image',
        'params':'none'
    },
    'PKGADD':
    {
        'description':'triggers if image contains a package that is not in its base',
        'params':'none'
    },
    'PKGDEL':
    {
        'description':'triggers if image has removed a package that is installed in its base',
        'params':'none'
    },
    'PKGDIFF':
    {
        'description':'triggers if any one of the other events has triggered',
        'params':'none'
    },
}


try:
    config = anchore.anchore_utils.init_gate_cmdline(sys.argv, gate_name, gate_help=triggers)
except Exception as err:
    print(str(err))
    sys.exit(1)

if not config:
    sys.exit(0)

imgid = config['imgid']

try:
    params = config['params']
except:
    params = None

if config['meta']['usertype'] != 'user':
    sys.exit(0)

outlist = list()

imageId = config['imgid']
baseId = config['baseid']

diffdata = anchore.anchore_utils.diff_images(imageId, baseId)
try:
    isdiff = False
    pkgdiffs = diffdata.pop('package_list', {}).pop('pkgs.all', {})
    for module_type in list(pkgdiffs.keys()):
        for pkg in list(pkgdiffs[module_type].keys()):
            isdiff = True
            status = pkgdiffs[module_type][pkg]
            if (status == 'VERSION_DIFF'):
                outlist.append('PKGVERSIONDIFF Package version in container is different from baseline for pkg - ' + pkg)
            elif (status == 'INIMG_NOTINBASE'):
                outlist.append("PKGADD Package has been added to image since base - " + pkg)
            elif (status == 'INBASE_NOTINIMG'):
                outlist.append("PKGDEL Package has been removed to image since base - " + pkg)

    if (isdiff):
        outlist.append("PKGDIFF Package manifest is different from image to base")
except Exception as err:
    print("ERROR: running gate " + gate_name + " failed: " + str(err))
    sys.exit(1)
    
anchore.anchore_utils.save_gate_output(imageId, gate_name, outlist)

sys.exit(0)
