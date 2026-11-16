"""FaceRegion - the working code. RE-IMPORTED on every command (hot reload).

Nothing may live in a module global between events: every handler recomputes from
the command inputs. The fitting maths is in fr_fit.py (no adsk, tested offline).

Dlab-IT007 section 5.4 step 2: mark the diaphysis, fit the best cylinder to it and
create it as a body. The axis is then Fusion's own Construct > Axis Through Cylinder.
Two ways to mark:

- Between two points: click the start and the end of the diaphysis on the bone. The
  area is the whole surface between the planes perpendicular to the bone axis through
  those points (3-matic's Area Mark, rectangle in a lateral view). Works on any body,
  including a 6-patch organic NURBS one, where a face is a quarter of the bone.
- Selected faces: on a faceted body (one face per triangle), Paint / Window selection
  plays the role of Brush / Area Mark.
"""

import adsk.core
import adsk.fusion

import datetime
import importlib
import json
import os
import sys

ADDIN_DIR = os.path.dirname(os.path.realpath(__file__))
if ADDIN_DIR not in sys.path:
    sys.path.insert(0, ADDIN_DIR)
import fr_fit  # noqa: E402
importlib.reload(fr_fit)

PANELS = ['SolidCreatePanel']
PREVIEW_ID = 'FaceRegion_preview'
MARKS_ID = 'FaceRegion_marks'
CONSTRUCTION_COMPONENT = 'Construcción'
CYLINDER_RGB = (30, 140, 255)       # preview and created cylinder share this blue
CYLINDER_OPACITY = 0.5              # see the bone through it: is it centred in the cortex?
APPEARANCE_NAME = 'FaceRegion - Cilindro'
APPEARANCE_LIB_ID = 'BA5EE55E-9982-449B-9D66-9F036540E140'    # Fusion Appearance Library
APPEARANCE_BASE_ID = 'Prism-374'    # ABS (White): plain opaque plastic, colour in opaque_albedo
MARK_RADIUS_CM = 0.1
ATTR_GROUP = 'FaceRegion'
MAX_FIT_POINTS = 3000
SAMPLE_SIDE_CM = 0.1        # 1 mm, the PNT's remesh size
EDGE_WARN_MM = 2.0          # the PNT remeshes to 1 mm before marking
MODE_POINTS = 'Between two points'
MODE_FACES = 'Selected faces'
SLAB_ITERATIONS = 5         # slab planes follow the fitted axis until it settles
SLAB_SETTLED_DEG = 0.01


# --------------------------------------------------------------------------- #
# toolbar
# --------------------------------------------------------------------------- #

def place_button(ui, cmd_def):
    """Add the button to PANELS. Returns the controls, for the shell to delete."""
    controls = []
    for pid in PANELS:
        panel = ui.allToolbarPanels.itemById(pid)
        if not panel:
            continue
        old = panel.controls.itemById(cmd_def.id)
        if old:
            old.deleteMe()
        ctrl = panel.controls.addCommand(cmd_def)
        ctrl.isPromotedByDefault = False
        controls.append(ctrl)
    return controls


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #

def _planar(face):
    return face.geometry.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType


def points_from_faces(faces):
    """Unique points of the faces. Planar faces (facets) give their vertices; any
    other face is tessellated with triangle sides capped at SAMPLE_SIDE_CM.

    The cap matters: tessellation follows curvature, so a face straight in one
    direction gets no points along it - a true cylinder (e.g. a 3-matic cylinder
    converted to a solid) came back as 24 points, all on its two end circles, and two
    clicks between them enclosed nothing. On a bone it also evens out the density,
    which was up to 3x higher at the curved ends than mid-shaft."""
    seen = set()
    pts = []

    def add(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key not in seen:
            seen.add(key)
            pts.append((x, y, z))

    for f in faces:
        if _planar(f):
            for v in f.vertices:
                p = v.geometry
                add(p.x, p.y, p.z)
        else:
            calc = f.meshManager.createMeshCalculator()
            calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.LowQualityTriangleMesh)
            calc.maxSideLength = SAMPLE_SIDE_CM
            xyz = calc.calculate().nodeCoordinatesAsDouble
            for i in range(0, len(xyz), 3):
                add(xyz[i], xyz[i + 1], xyz[i + 2])
    return pts


def mean_edge_mm(faces):
    """Mean facet edge length. Only planar faces count: the edges of a NURBS patch
    are patch borders, not mesh resolution."""
    total, n = 0.0, 0
    for f in faces:
        if not _planar(f):
            continue
        for e in f.edges:
            total += e.length
            n += 1
    return 10.0 * total / n if n else 0.0


def _sample(pts):
    return fr_fit.sample(pts, MAX_FIT_POINTS)


def analyse(faces):
    """Fit a cylinder to the selected faces. Raises ValueError with a message."""
    if not faces:
        raise ValueError('Select the faces of the diaphysis.')
    body = faces[0].body
    for f in faces[1:]:
        if not f.body == body:
            raise ValueError('The faces belong to more than one body. Fit one bone at a '
                             'time: a cylinder over two diaphyses fits neither.')
    pts = points_from_faces(faces)
    if len(pts) < 12:
        raise ValueError('Only %d points selected - mark more of the diaphysis.' % len(pts))
    sample = _sample(pts)
    fit = fr_fit.fit_cylinder(sample)
    inertia = fr_fit.inertia_axes(sample)[0][0]
    return {'mode': 'faces', 'fit': fit, 'body': body, 'faces': len(faces),
            'points': len(pts), 'fit_points': len(sample), 'edge_mm': mean_edge_mm(faces),
            'inertia_angle': fr_fit.angle_deg(fit['direction'], inertia),
            'in_assembly': faces[0].assemblyContext is not None}


def analyse_slab(body, p1, p2, in_assembly=False):
    """Fit a cylinder to the whole surface of body between two clicked points
    (fr_fit.fit_slab: planes perpendicular to the bone axis, re-cut until it settles)."""
    faces = list(body.faces)
    pts = points_from_faces(faces)
    fit, slab, iters, inertia = fr_fit.fit_slab(pts, p1, p2, MAX_FIT_POINTS,
                                                SLAB_ITERATIONS, SLAB_SETTLED_DEG)
    d = fit['direction']
    # percentages count from the bone end on the From side
    if fr_fit._dot(fr_fit._sub(p2, p1), d) < 0:
        d = fr_fit._mul(d, -1.0)
    ts = [fr_fit._dot(p, d) for p in pts]
    t_lo, t_hi = min(ts), max(ts)
    span = (t_hi - t_lo) or 1.0
    a, b = (fr_fit._dot(p1, d) - t_lo) / span, (fr_fit._dot(p2, d) - t_lo) / span
    return {'mode': 'points', 'fit': fit, 'body': body, 'faces': len(faces),
            'points': len(slab), 'fit_points': len(_sample(slab)),
            'edge_mm': mean_edge_mm(faces),
            'inertia_angle': fr_fit.angle_deg(fit['direction'], inertia),
            'in_assembly': in_assembly, 'iterations': iters,
            'slab_pct': (100.0 * a, 100.0 * b), 'bone_length_mm': span * 10}


def cylinder_body(fit, extend_cm=0.0, to_local=None):
    """Temporary BRep cylinder over the points' extent along the axis, plus extend.
    to_local: matrix taking the (root space) fit into the target component's space."""
    d = fit['direction']
    s = fr_fit._sub(fit['start'], fr_fit._mul(d, extend_cm))
    e = fr_fit._add(fit['end'], fr_fit._mul(d, extend_cm))
    ps, pe = adsk.core.Point3D.create(*s), adsk.core.Point3D.create(*e)
    if to_local:
        ps.transformBy(to_local)
        pe.transformBy(to_local)
    tbm = adsk.fusion.TemporaryBRepManager.get()
    return tbm.createCylinderOrCone(ps, fit['radius'], pe, fit['radius'])


def construction_component(design):
    """The component that holds every fitted cylinder, created on first use.

    Fusion's construction geometry is planes, axes and points only, so a cylinder can't
    be one. A component of its own is the closest: a separate node in the browser,
    hidden or shown as a unit, away from the bones. Returns (component, matrix from root
    space to its space) - the matrix is not identity if the user moved it."""
    root = design.rootComponent
    for occ in root.occurrences:
        if occ.component.name == CONSTRUCTION_COMPONENT:
            break
    else:
        occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occ.component.name = CONSTRUCTION_COMPONENT
    to_local = occ.transform2.copy()
    to_local.invert()
    return occ.component, to_local


def cylinder_appearance(design):
    """The design's cylinder appearance, copied from the library and recoloured on first
    use, reused by name afterwards (so a colour the user changes in Fusion sticks).
    Library and appearance are found by id: their names follow the UI language."""
    existing = design.appearances.itemByName(APPEARANCE_NAME)
    if existing:
        return existing
    lib = adsk.core.Application.get().materialLibraries.itemById(APPEARANCE_LIB_ID)
    base = lib.appearances.itemById(APPEARANCE_BASE_ID) if lib else None
    if base is None:
        return None
    appearance = design.appearances.addByCopy(base, APPEARANCE_NAME)
    color = adsk.core.ColorProperty.cast(appearance.appearanceProperties.itemById('opaque_albedo'))
    if color:
        color.value = adsk.core.Color.create(*CYLINDER_RGB, 255)
    return appearance


def style_cylinder(body, appearance):
    """Colour and opacity (a body setting, as right-click Opacity Control, so the user
    can change it). In a parametric design call this on the body INSIDE the base
    feature edit: set on the body after finishEdit, both are dropped at the next
    recompute (reopening the file, an upstream edit) - that is how a cylinder made on
    2026-10-28 came back grey and opaque. Set inside the edit, they persist."""
    if appearance:
        body.appearance = appearance
    body.opacity = CYLINDER_OPACITY


def restyle_cylinder(design, body):
    """Re-apply colour and opacity to an existing FaceRegion cylinder so they persist:
    reopen its base feature, set them on the body inside, close it again."""
    appearance = cylinder_appearance(design)
    native = body.nativeObject or body
    base = None
    if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        for bf in native.parentComponent.features.baseFeatures:
            if any(bf.bodies.item(i) == native for i in range(bf.bodies.count)):
                base = bf
                break
    if base is None:
        style_cylinder(native, appearance)
        return
    base.startEdit()
    for i in range(base.bodies.count):
        style_cylinder(base.bodies.item(i), appearance)
    base.finishEdit()


def create_cylinder(design, res, name, extend_cm=0.0):
    """Add the cylinder as a body of the construction component. Parametric designs
    get it in a base feature. The fit is in root space (picked points and face proxies
    are), whatever component the bone lives in."""
    comp, to_local = construction_component(design)
    tmp = cylinder_body(res['fit'], extend_cm, to_local)
    appearance = cylinder_appearance(design)
    if design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        base = comp.features.baseFeatures.add()
        base.startEdit()
        inner = comp.bRepBodies.add(tmp, base)
        style_cylinder(inner, appearance)
        base.finishEdit()
        base.name = name
        # the body handed back inside the edit does not survive finishEdit
        body = base.bodies.item(0)
    else:
        body = comp.bRepBodies.add(tmp)
        style_cylinder(body, appearance)
    body.name = name
    f = res['fit']
    record = {'source_body': res['body'].name, 'mode': res['mode'], 'faces': res['faces'],
              'points': res['points'], 'fit_points': res['fit_points'],
              'radius_mm': f['radius'] * 10, 'rms_mm': f['rms'] * 10,
              'max_mm': f['max_abs'] * 10, 'length_mm': f['length'] * 10,
              'extend_mm': extend_cm * 10, 'inertia_angle_deg': res['inertia_angle'],
              'mean_edge_mm': res['edge_mm'],
              'created': datetime.datetime.now().isoformat(timespec='seconds')}
    if res['mode'] == 'points':
        record['slab_pct'] = res['slab_pct']
        record['bone_length_mm'] = res['bone_length_mm']
    body.attributes.add(ATTR_GROUP, 'fit', json.dumps(record))
    return body


def report(res):
    f = res['fit']
    if res['mode'] == 'points':
        head = ('<b>%s</b>: %.0f%%–%.0f%% of the bone length (%.0f mm), %d points'
                % (res['body'].name, res['slab_pct'][0], res['slab_pct'][1],
                   res['bone_length_mm'], res['points']))
    else:
        head = '<b>%s</b>: %d faces, %d points' % (res['body'].name, res['faces'],
                                                   res['points'])
    lines = [
        head,
        'R <b>%.2f mm</b> (Ø %.2f), length %.1f mm' % (f['radius'] * 10, f['radius'] * 20,
                                                     f['length'] * 10),
        'Fit error: RMS %.2f mm, max %.2f mm' % (f['rms'] * 10, f['max_abs'] * 10),
        'Angle to inertia axis: %.2f°' % res['inertia_angle'],
    ]
    if f['flat']:
        lines.append('<b>Not a bone axis:</b> the area is too flat for a cylinder along it. '
                     'Mark further round the diaphysis.')
    if res['edge_mm'] > EDGE_WARN_MM:
        lines.append('<i>Mean edge %.1f mm: coarse mesh (procedure remeshes to 1 mm).</i>'
                     % res['edge_mm'])
    return '<br>'.join(lines)


# --------------------------------------------------------------------------- #
# preview graphics - found by id, never held in a global
# --------------------------------------------------------------------------- #

def clear_preview(app, gid=PREVIEW_ID):
    des = adsk.fusion.Design.cast(app.activeProduct)
    if not des:
        return
    groups = des.rootComponent.customGraphicsGroups
    for i in range(groups.count - 1, -1, -1):
        g = groups.item(i)
        if g.id == gid:
            g.deleteMe()


def show_marks(app, points):
    """Small spheres at the stored From / To points. Drawn from inputChanged, not
    from the preview, so From shows before there is anything to fit."""
    clear_preview(app, MARKS_ID)
    if not points:
        return
    des = adsk.fusion.Design.cast(app.activeProduct)
    group = des.rootComponent.customGraphicsGroups.add()
    group.id = MARKS_ID
    tbm = adsk.fusion.TemporaryBRepManager.get()
    for p, rgb in zip(points, ((0, 170, 80), (230, 60, 40))):
        cg = group.addBRepBody(tbm.createSphere(adsk.core.Point3D.create(*p), MARK_RADIUS_CM))
        cg.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
            adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255))
        cg.isSelectable = False
    app.activeViewport.refresh()


def show_preview(app, res, extend_cm):
    clear_preview(app)
    des = adsk.fusion.Design.cast(app.activeProduct)
    group = des.rootComponent.customGraphicsGroups.add()
    group.id = PREVIEW_ID
    cg = group.addBRepBody(cylinder_body(res['fit'], extend_cm))
    cg.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(*CYLINDER_RGB, 110))
    cg.isSelectable = False
    app.activeViewport.refresh()


# --------------------------------------------------------------------------- #
# command handlers (called by the shell)
# --------------------------------------------------------------------------- #

def _mode(inputs):
    return inputs.itemById('mode').selectedItem.name


def _faces(inputs):
    sel = inputs.itemById('faces')
    return [adsk.fusion.BRepFace.cast(sel.selection(i).entity)
            for i in range(sel.selectionCount)]


def _picks(inputs):
    """The stored clicks: {'from': xyz, 'to': xyz, 'body': token, 'asm': bool}, or {}.

    Fusion lets an entity be selected only once per command, and clicking a selected
    face deselects it, so From and To on the same face (a NURBS bone puts the whole
    diaphysis in one face) can't both stay selected. Each click is therefore recorded
    here and its selection cleared, leaving the face free for the next click."""
    raw = inputs.itemById('picks').value
    return json.loads(raw) if raw else {}


def _save_picks(inputs, picks):
    inputs.itemById('picks').value = json.dumps(picks) if picks else ''


def _pick_body(picks):
    des = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    found = des.findEntityByToken(picks['body'])
    if not found:
        raise ValueError('The bone picked for From is no longer there - start again.')
    return adsk.fusion.BRepBody.cast(found[0])


def _extend_cm(inputs):
    return inputs.itemById('extend').value


def _current(inputs):
    """Analysis for whichever mode is active. Raises ValueError with a message."""
    if _mode(inputs) == MODE_FACES:
        return analyse(_faces(inputs))
    picks = _picks(inputs)
    if not picks.get('from'):
        raise ValueError('Click on the bone where the diaphysis starts (From).')
    if not picks.get('to'):
        raise ValueError('From is set (green) on <b>%s</b>. Now click where the diaphysis '
                         'ends (To) - the same face is fine. Wrong body? Click again to '
                         'restart.' % _pick_body(picks).name)
    return analyse_slab(_pick_body(picks), tuple(picks['from']), tuple(picks['to']),
                        picks['asm'])


def _body(inputs):
    if _mode(inputs) == MODE_FACES:
        return _faces(inputs)[0].body
    return _pick_body(_picks(inputs))


def _record_pick(app, inputs):
    """Turn the click in the 'pick' input into From or To, then free the selection.
    1st click = From, 2nd = To, a 3rd starts again from From."""
    sel = inputs.itemById('pick')
    if sel.selectionCount == 0:            # our own clearSelection() echoing back
        return False
    s = sel.selection(0)
    face = adsk.fusion.BRepFace.cast(s.entity)
    p = (s.point.x, s.point.y, s.point.z)
    picks = _picks(inputs)
    if picks.get('from') and not picks.get('to'):
        picks['to'] = p
    else:
        picks = {'from': p, 'to': None, 'body': face.body.entityToken,
                 'asm': face.assemblyContext is not None}
    _save_picks(inputs, picks)
    sel.clearSelection()
    show_marks(app, [q for q in (picks['from'], picks['to']) if q])
    return True


def _store(inputs, res=None, error=None):
    """Keep the analysis in a hidden input. A fit takes 1-3 s, and Fusion fires
    validate and preview after every change: they read this instead of refitting.
    It lives in the command, not in a module global, so the hot reload can't lose it."""
    if error is not None:
        state = {'error': error}
    else:
        state = {k: v for k, v in res.items() if k != 'body'}
    inputs.itemById('state').value = json.dumps(state)


def _stored(inputs):
    """The analysis stored by on_input_changed, with the body re-attached, or None."""
    raw = inputs.itemById('state').value
    if not raw:
        return None
    state = json.loads(raw)
    if 'error' in state:
        return None
    state['body'] = _body(inputs)
    return state


def _show_mode(app, inputs):
    points = _mode(inputs) == MODE_POINTS
    inputs.itemById('pick').isVisible = points
    inputs.itemById('reset').isVisible = points
    inputs.itemById('faces').isVisible = not points
    picks = _picks(inputs)
    show_marks(app, [q for q in (picks.get('from'), picks.get('to')) if q] if points else [])


def on_created(app, cmd):
    inputs = cmd.commandInputs
    mode = inputs.addDropDownCommandInput('mode', 'Mark', adsk.core.DropDownStyles.TextListDropDownStyle)
    mode.listItems.add(MODE_POINTS, True)
    mode.listItems.add(MODE_FACES, False)
    sel = inputs.addSelectionInput(
        'pick', 'From / To',
        'Click on the bone where the diaphysis starts (From, green), then where it ends '
        '(To, red). Both can be on the same face. A third click starts again. The whole '
        'surface between the two points, all the way round, is fitted.')
    sel.addSelectionFilter('SolidFaces')
    sel.setSelectionLimits(0, 1)
    inputs.addBoolValueInput('reset', 'Start again', True, '', False)
    inputs.addStringValueInput('picks', 'picks', '').isVisible = False
    sel = inputs.addSelectionInput(
        'faces', 'Diaphysis',
        'Faces of the diaphysis on one faceted body. Use Paint or Window selection '
        '(Select menu) like Brush / Area Mark; leave out the metaphysis and epiphysis.')
    sel.addSelectionFilter('SolidFaces')
    sel.setSelectionLimits(0, 0)
    inputs.addStringValueInput('name', 'Body name', '')
    inputs.addValueInput('extend', 'Extend each end', 'mm',
                         adsk.core.ValueInput.createByReal(0.0))
    inputs.addTextBoxCommandInput('report', 'Fit', 'Click the start and the end of the '
                                  'diaphysis on the bone.', 6, True)
    inputs.addStringValueInput('state', 'state', '').isVisible = False
    _show_mode(app, inputs)
    cmd.okButtonText = 'Create cylinder'
    cmd.setDialogMinimumSize(360, 280)


def _is_ours(body):
    native = body.nativeObject or body       # attributes live on the native body
    return native.attributes.itemByName(ATTR_GROUP, 'fit') is not None


def on_pre_select(inputs, entity, active_id):
    """Only faces of the bone already being marked are selectable, and never a
    cylinder this add-in made (it sits on the bone and would catch the clicks)."""
    face = adsk.fusion.BRepFace.cast(entity)
    if face is None or _is_ours(face.body):
        return False
    if active_id == 'pick':
        picks = _picks(inputs)
        if picks.get('from') and not picks.get('to'):     # To: same bone as From
            try:
                return face.body == _pick_body(picks)
            except ValueError:
                return True
        return True
    faces = _faces(inputs)
    return not faces or face.body == faces[0].body


def on_input_changed(app, inputs, input_id):
    """The only place that fits. Extend and name changes reuse the stored fit."""
    if input_id == 'mode':
        _show_mode(app, inputs)
    elif input_id == 'pick':
        if not _record_pick(app, inputs):
            return
    elif input_id == 'reset':
        box = inputs.itemById('reset')
        if not box.value:                  # our own untick echoing back
            return
        box.value = False
        _save_picks(inputs, {})
        show_marks(app, [])
    elif input_id != 'faces':
        return
    box = inputs.itemById('report')
    try:
        res = _current(inputs)
    except ValueError as e:
        _store(inputs, error=str(e))
        box.formattedText = str(e)
        return
    _store(inputs, res)
    name = inputs.itemById('name')
    if not name.value:
        name.value = 'Cilindro ' + res['body'].name.replace(' [part]', '')
    box.formattedText = report(res)


def on_validate(inputs):
    res = _stored(inputs)
    return bool(res and not res['fit']['flat'] and inputs.itemById('name').value.strip())


def on_preview(app, cmd):
    """The preview cylinder, and the From / To marks again: marks drawn in inputChanged
    are dropped by Fusion at its next preview cycle, so after a valid fit they vanished
    at the first change (Extend, name) - fixed 2026-11-02 (same cause as FacePoint v0.1).
    inputChanged still draws them for the states without a preview (only From set)."""
    inputs = cmd.commandInputs
    res = _stored(inputs)
    if res and not res['fit']['flat']:
        show_preview(app, res, _extend_cm(inputs))
    else:
        clear_preview(app)
    if _mode(inputs) == MODE_POINTS:
        picks = _picks(inputs)
        show_marks(app, [q for q in (picks.get('from'), picks.get('to')) if q])


def on_execute(app, ui, cmd):
    clear_preview(app)
    clear_preview(app, MARKS_ID)
    inputs = cmd.commandInputs
    des = adsk.fusion.Design.cast(app.activeProduct)
    create_cylinder(des, _stored(inputs), inputs.itemById('name').value.strip(),
                    _extend_cm(inputs))


def on_destroy(app):
    clear_preview(app)
    clear_preview(app, MARKS_ID)
