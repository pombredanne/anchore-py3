import sys
import click

from anchore import analyzer, controller, anchore_utils
from anchore.cli.common import build_image_list, anchore_print, anchore_print_err, extended_help_option
from anchore.util import contexts


gate_extended_help = """
Run gate analysis on the specified images with the specified options or else edits the policy that is effective for a specific image or
all images. Anchore gates are a set of checks against the image, image's dockerfile and other data sources (e.g. CVEs). The default gate policy
file is found in $anchore/conf/anchore_gate.policy, where $anchore = $HOME/.anchore (default) or /etc/anchore depending on installation.

Image IDs can be specified as hash ids, repo names (e.g. centos), or tags (e.g. centos:latest).

See the policy file for the set of available gates and their triggers.

\b
The output of each gate is one of:
* GO - Check is ok, no trigger fired
* STOP - Trigger found something. Policy says to output a stop
* WARN - Emit a warning to flag this as something to follow-up on.

The gate results are only output to the user, so their meaning is entirely up to the user. A typical use would be to
not push any container image to production if it has any 'STOP' gate results. But, how to use the gate output is entirely
up to the user.

Editing Gate Policies:

Anchore has a global gate policy document, but this can be overridden for each individual image if desired by
running '--editpolicy' for the desired image. The policy file opened for editing will be specific to the image.
A gate policy file is composed of lines of the following format:

<Gate Name>:<Trigger Name>:<Result if triggered>

Gate Policy Example:

``DOCKERFILECHECK:NOFROM:STOP`` specifies a check against an image's dockerfile (if available) such that if the 'NOFROM' trigger evaluates to true then the gate action will be 'STOP'


Usage Examples:

View gate output for the 'node:latest' image:
'anchore gate --image node:latest'

View gate output for all images:
'anchore gate'

Edit the gate policy for 'nginx:latest':
'anchore gate --image nginx:latest --editpolicy'

"""


@click.command(short_help='Perform and view gate evaluation on selected images')
@click.option('--force', is_flag=True, help='Force gates to run even if they already have.')
@click.option('--image', help='Process specified image ID. Cannot be combined with --imagefile', metavar='<imageid>')
@click.option('--imagefile', help='Process image IDs listed in specified file. Cannot be combined with --image', type=click.Path(exists=True), metavar='<file>')
@click.option('--include-allanchore', help='Include all images known by anchore', is_flag=True)
@click.option('--editpolicy', is_flag=True, help='Edit the gate policies for specified image(s).')
@click.option('--rmpolicy', is_flag=True, help='Delete the policies for specified image(s), revert to default policy.')
@click.option('--listpolicy', is_flag=True, help='List the current gate policy for specified image(s).')
@click.option('--updatepolicy', help='Store the input gate policy file as the policy for specified image(s).', type=click.Path(exists=True), metavar='<file>')
@click.option('--policy', help='Use the specified policy file instead of the default.', type=click.Path(exists=True), metavar='<file>')
@click.option('--show-gatehelp', help='Show all gate names, triggers, and params that can be used to build an anchore policy', is_flag=True)
@click.option('--show-policytemplate', help='Generate policy template based on all installed gate/triggers', is_flag=True)
@click.option('--whitelist', is_flag=True, help='Edit evaluated gate triggers and optionally whitelist them.')
@click.pass_obj
@extended_help_option(extended_help=gate_extended_help)
def gate(anchore_config, force, image, imagefile, include_allanchore, editpolicy, rmpolicy, listpolicy, updatepolicy, policy, show_gatehelp, show_policytemplate, whitelist):
    """
    Runs gate checks on the specified image(s) or edits the image's gate policy.
    The --editpolicy option is only valid for a single image.

    The --image and --imagefile options are mutually exclusive.

    Image IDs can be specified as hash ids, repo names (e.g. centos), or tags (e.g. centos:latest).
    """

    ecode = 0
    success = True

    # special option, does not need any image inputs
    if show_gatehelp:
        try:
            gate_info = anchore_utils.discover_gates()
            anchore_print(gate_info, do_formatting=True)
        except Exception as err:
            anchore_print_err("operation failed: " + str(err))
            sys.exit(1)
        sys.exit(0)

    if show_policytemplate:
        try:
            outstr = "\n"
            gate_info = anchore_utils.discover_gates()
            for g in list(gate_info.keys()):
                for t in list(gate_info[g].keys()):
                    params = list()
                    if 'params' in gate_info[g][t] and gate_info[g][t]['params'] and gate_info[g][t]['params'].lower() != 'none':
                        for p in gate_info[g][t]['params'].split(','):
                            params.append(p+"=<a,b,c>")
                        
                    outstr += ':'.join([g, t, "<STOP|WARN|GO>", ' '.join(params)]) + "\n"
            
            anchore_print(outstr, do_formatting=False)
        except Exception as err:
            anchore_print_err("operation failed: " + str(err))
            sys.exit(1)
        sys.exit(0)

    # the rest require some form of image(s) be given as input
    if image and imagefile:
        raise click.BadOptionUsage('Can only use one of --image, --imagefile')

    if policy and (editpolicy or whitelist or listpolicy or updatepolicy or rmpolicy):
        raise click.BadOptionUsage('Cannot use other policy options when --policy <file> is specified.')

    try:
        imagedict = build_image_list(anchore_config, image, imagefile, not (image or imagefile), include_allanchore)
        imagelist = list(imagedict.keys())

        try:
            ret = anchore_utils.discover_imageIds(imagelist)
        except ValueError as err:
            raise err
        else:
            #imagelist = ret.keys()
            imagelist = ret

    except Exception as err:
        anchore_print_err("could not load any images")
        sys.exit(1)

    try:
        con = controller.Controller(anchore_config=anchore_config, imagelist=imagelist, allimages=contexts['anchore_allimages'], force=force)
    except Exception as err:
        anchore_print_err("gate operation failed")
        ecode = 1
    else:
        if editpolicy:
            if not con.editpolicy():
                ecode = 1
        elif whitelist:
            if not con.editwhitelist():
                ecode = 1
        elif rmpolicy:
            if not con.rmpolicy():
                ecode = 1;
            else:
                anchore_print("policies successfully removed.", do_formatting=True)
        elif updatepolicy:
            if not con.updatepolicy(updatepolicy):
                ecode = 1;
            else:
                anchore_print("policies successfully updated.", do_formatting=True)
        elif listpolicy:
            result = con.listpolicy()
            record = {}
            if not result:
                ecode = 1
            else:
                try:
                    for imageId in list(result.keys()):
                        record[imageId] = list()
                        pol = result[imageId]
                        for gate in list(pol.keys()):
                            for trigger in list(pol[gate].keys()):
                                if str(pol[gate][trigger]['params']):
                                    outstr = ":".join([gate, trigger, str(pol[gate][trigger]['action']), str(pol[gate][trigger]['params'])])
                                else:
                                    outstr = ":".join([gate, trigger, str(pol[gate][trigger]['action'])])
                                record[imageId].append(outstr)
                    if record:
                        anchore_print(record, do_formatting=True)
                except Exception as err:
                    anchore_print_err("failed to list policies: " + str(err))
                    ecode = 1
        else:
            try:
                # run the gates
                result = con.run_gates(policy=policy)
                if result:
                    anchore_utils.print_result(anchore_config, result)
                    success = True
                    ecode = con.result_get_highest_action(result)
            except Exception as err:
                anchore_print_err("failed to run gates: " + str(err))
                ecode = 1

    contexts['anchore_allimages'].clear()
    sys.exit(ecode)


analyze_extended_help = """
Run the analyzer to scan and summarize a container image and store that analysis in the local host's anchore image db for further use in gating, reports, and queries.

Upon completion of analysis of an image there will be an entry in the
db named with the imageid (a directory in $anchore/data/, where
$anchore = $HOME/.anchore (default) or /etc/anchore depending on
installation). If the analyzer detects that an image has already been
analyzed it will skip analysis. This behavior can be overridden with
the '--force' flag.

To get the full power of analysis and subsequent gate and query tools
it is recommended to include the dockerfile as often as possible.
When using --dockerfile, you must use --image and specify a single
image. This allows anchore to associate that specific dockerfile with
the image in the analysis output. Anchore will always try to infer a
dockerfile, but certain constructs and operations in dockerfiles
become opaque after the image is built (e.g. COPY operations, or RUN
operations that invoke a tool that loads data on the image), so
including the actual dockerfile results in the best analysis output
and makes more information available for gate evaluation and later
queries.

Image IDs can be specified as hash ids, repo names (e.g. centos), or tags (e.g. centos:latest).

Image Types: ["none"|"base"]
Specify the type of the image being analyzed. Use 'base' to tell anchore that the given image is a base image to be
used to build other images. Use 'none' to not assign a specific image type to the image.


Examples:

Analyze all images listed in a file that contains lines of the form '<image ID> <path/to/dockerfile>' on the local host:

'anchore analyze --imagefile myimages.txt'

Analyze a newly built image with it's corresponding dockerfile:

'anchore analyze --image myapp:latest --dockerfile myapp.dockerfile'

Analyze all image on the local host except a list (perhaps local tools used in the build process, etc):

'anchore analyze --excludefile exclusions.txt'
"""


@click.command(short_help='Perform analysis on specified image IDs.')
@click.option('--force', is_flag=True, help='Force analysis even if existing analysis is found in db.')
@click.option('--image', help='Process specified image ID', metavar='<imageid>')
@click.option('--imagefile', help='Process image IDs listed in specified file.', type=click.Path(exists=True), metavar='<file>')
@click.option('--include-allanchore', help='Include all images known by anchore, as found in host-local db', is_flag=True)
#@click.option('--imagetar', help='Use with --image if you have a tar of the image instead of having anchore save from docker', type=click.Path(exists=True), metavar='<file>')
@click.option('--dockerfile', help='Dockerfile of the image to analyze.', type=click.Path(exists=True), metavar='<file>')
@click.option('--imagetype', help='Specify the type of image that is being analyzed (use "none" if unknown).', metavar='<typetext>')
@click.option('--skipgates', is_flag=True, help='Do not run gates as part of analysis.')
@click.option('--excludefile', help='Name of file containing images to exclude during analysis. Each line is an image name/id', type=click.Path(exists=True), metavar='<file>')
@click.pass_obj
@extended_help_option(extended_help=analyze_extended_help)
def analyze(anchore_config, force, image, imagefile, include_allanchore, dockerfile, imagetype, skipgates, excludefile):
    """
    Invokes the anchore analyzer on the specified image(s).

    To include multiple images use the --imagefile, no option, or --include-allanchore options.
    To exclude specific images from analysis, use the --excludefile option.

    One of --imagetype or --dockerfile are required for an analysis run. Use --dockerfile whenever possible as the inclusion
    of the dockerfile for an image associates the dockerfile and image for later use in queries etc. The --dockerfile option
    is only valid in combination with the --image option.

    When using --imagetype, use 'none' to specify that the image(s) is an unknown or user image and use 'base' to specify
    that the image(s) are approved base images to be used to build other images--'golden' images.

    Image IDs can be specified as hash ids, repo names (e.g. centos), or tags (e.g. centos:latest).

    """

    success = True
    ecode = 0

    args = {}

    if image and imagefile:
        raise click.BadOptionUsage('Can only use one of --image, --imagefile')

    if dockerfile and not image:
        raise click.BadOptionUsage('Must specify --image option when using --dockerfile option')

    if not imagefile:
        if imagetype:
            if imagetype == "anchorebase":
                args['anchorebase'] = True
            elif imagetype == "base":
                args['isbase'] = True
            elif imagetype == "none":
                pass
            else:
                raise click.BadOptionUsage("Invalid imagetype specified: valid types are 'none' or 'base'")
        elif not dockerfile:
            raise click.BadOptionUsage('Must specify either --dockerfile or --imagetype <type>')

    try:
        imagedict = build_image_list(anchore_config, image, imagefile, not (image or imagefile), include_allanchore, exclude_file=excludefile, dockerfile=dockerfile)
        imagelist = list(imagedict.keys())

        try:
            ret = anchore_utils.discover_imageIds(imagelist)
        except ValueError as err:
            raise err
        else:
            #imagelist = ret.keys()
            imagelist = ret

    except Exception as err:
        anchore_print_err("could not load any images")
        ecode = 1
    else:

        step = 1
        count = 0
        allimages = {}
        for imageId in list(imagedict.keys()):

            if count % step == 0:
                allimages.clear()
                allimages = {}
                count = 0

            args.update({'dockerfile': imagedict[imageId]['dockerfile'], 'skipgates': skipgates})

            inlist = [imageId]
            try:
                anchore_print("Analyzing image: " + imageId)
                success = analyzer.Analyzer(anchore_config=anchore_config, imagelist=inlist, allimages=allimages, force=force, args=args).run()
            except:
                anchore_print_err('failed to run analyzer')
                allimages.clear()
                success = False
                ecode = 1
                break

            count = count + 1

        allimages.clear()

        if not success:
            ecode = 1

    sys.exit(ecode)
