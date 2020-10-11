# Copyright 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import sys, random, os
import bpy, bpy_extras
from mathutils import Vector, Matrix

"""
Some utility functions for interacting with Blender
"""


def extract_args(input_argv=None):
  """
  Pull out command-line arguments after "--". Blender ignores command-line flags
  after --, so this lets us forward command line arguments from the blender
  invocation to our own script.
  """
  if input_argv is None:
    input_argv = sys.argv
  output_argv = []
  if '--' in input_argv:
    idx = input_argv.index('--')
    output_argv = input_argv[(idx + 1):]
  return output_argv


def parse_args(parser, argv=None):
  return parser.parse_args(extract_args(argv))


# I wonder if there's a better way to do this?
def delete_object(obj):
  """ Delete a specified blender object """
  for o in bpy.data.objects:
    o.select = False
  obj.select = True
  bpy.ops.object.delete()

def image2world(cam, im_pos, scene):
  from mathutils import Vector

  (x, y, z) = im_pos
  camera = cam.data

  frame = [-v for v in camera.view_frame(scene=scene)[:3]]


  if camera.type != 'ORTHO':
      if x == 0.5 and y == 0.5 and z == 0.0:
          return Vector((0.5, 0.5, 0.0))
      else:
          frame = [(v / (v.z / z)) for v in frame]

  min_x, max_x = frame[1].x, frame[2].x
  min_y, max_y = frame[0].y, frame[1].y

  cx = x*(max_x-min_x)+min_x
  cy = y*(max_y-min_y)+min_y

  vec = Vector((cx, cy, -z))

  # print(im_pos)
  # print(vec)
  # print([list(v) for v in list(cam.matrix_world.normalized())])
  # print(vec*cam.matrix_world.normalized())
  # print(cam.matrix_world.normalized()*vec)

  return cam.matrix_world.normalized() * vec

def important_data(cam):
  scene = bpy.context.scene
  camera = cam.data
  frame = [-v for v in camera.view_frame(scene=scene)[:3]]
  important_data = {"frame": [(fr.x, fr.y, fr.z) for fr in frame]}
  important_data["matrix_world"] = [list(v) for v in list(cam.matrix_world.normalized())]
  important_data["int"] = intrinsic_mat(camera)
  return important_data

def intrinsic_mat(cam):
    # get the relevant data
  scene = bpy.context.scene
  # assume image is not scaled
  assert scene.render.resolution_percentage == 100
  # assume angles describe the horizontal field of view
  assert cam.sensor_fit != 'VERTICAL'

  f_in_mm = cam.lens
  sensor_width_in_mm = cam.sensor_width

  w = scene.render.resolution_x
  h = scene.render.resolution_y

  pixel_aspect = scene.render.pixel_aspect_y / scene.render.pixel_aspect_x

  f_x = f_in_mm / sensor_width_in_mm * w
  f_y = f_x * pixel_aspect

  # yes, shift_x is inverted. WTF blender?
  c_x = w * (0.5 - cam.shift_x)
  # and shift_y is still a percentage of width..
  c_y = h * 0.5 + w * cam.shift_y

  K = [[f_x, 0, c_x],
       [0, f_y, c_y],
       [0,   0,   1]]
  return [f_x, f_y, c_x, c_y]


def get_camera_coords(cam, pos):
  """
  For a specified point, get both the 3D coordinates and 2D pixel-space
  coordinates of the point from the perspective of the camera.

  Inputs:
  - cam: Camera object
  - pos: Vector giving 3D world-space position

  Returns a tuple of:
  - (px, py, pz): px and py give 2D image-space coordinates; pz gives depth
    in the range [-1, 1]
  """
  scene = bpy.context.scene
  x, y, z = bpy_extras.object_utils.world_to_camera_view(scene, cam, pos)
  scale = scene.render.resolution_percentage / 100.0
  w = int(scale * scene.render.resolution_x)
  h = int(scale * scene.render.resolution_y)
  px = int(round(x * w))
  py = int(round(h - y * h))

  res = image2world(cam, (x,y,z), scene)
  d1, d2, d3 = res-pos
  assert d1+d2+d3 <= 0.001, cam.location
  # print(x, y, px/w, (h-py)/h, w, h)

  return (px, py, z)


def set_layer(obj, layer_idx):
  """ Move an object to a particular layer """
  # Set the target layer to True first because an object must always be on
  # at least one layer.
  obj.layers[layer_idx] = True
  for i in range(len(obj.layers)):
    obj.layers[i] = (i == layer_idx)


def add_object(object_dir, name, scale, loc, theta=0):
  """
  Load an object from a file. We assume that in the directory object_dir, there
  is a file named "$name.blend" which contains a single object named "$name"
  that has unit size and is centered at the origin.

  - scale: scalar giving the size that the object should be in the scene
  - loc: tuple (x, y) giving the coordinates on the ground plane where the
    object should be placed.
  """
  # First figure out how many of this object are already in the scene so we can
  # give the new object a unique name
  count = 0
  for obj in bpy.data.objects:
    if obj.name.startswith(name):
      count += 1

  filename = os.path.join(object_dir, '%s.blend' % name, 'Object', name)
  bpy.ops.wm.append(filename=filename)

  # Give it a new name to avoid conflicts
  new_name = '%s_%d' % (name, count)
  bpy.data.objects[name].name = new_name

  # Set the new object as active, then rotate, scale, and translate it
  bpy.context.scene.objects.active = bpy.data.objects[new_name]
  bpy.context.object.rotation_euler[2] = theta
  bpy.ops.transform.resize(value=(scale, scale, scale))
  # modified from CLEVR: y-axis is 0, and blocks are stacked vertically
  bpy.ops.transform.translate(value=tuple(loc))


def load_materials(material_dir):
  """
  Load materials from a directory. We assume that the directory contains .blend
  files with one material each. The file X.blend has a single NodeTree item named
  X; this NodeTree item must have a "Color" input that accepts an RGBA value.
  """
  for fn in os.listdir(material_dir):
    if not fn.endswith('.blend'): continue
    name = os.path.splitext(fn)[0]
    filepath = os.path.join(material_dir, fn, 'NodeTree', name)
    bpy.ops.wm.append(filename=filepath)


def add_material(name, **properties):
  """
  Create a new material and assign it to the active object. "name" should be the
  name of a material that has been previously loaded using load_materials.
  """
  # Figure out how many materials are already in the scene
  mat_count = len(bpy.data.materials)

  # Create a new material; it is not attached to anything and
  # it will be called "Material"
  bpy.ops.material.new()

  # Get a reference to the material we just created and rename it;
  # then the next time we make a new material it will still be called
  # "Material" and we will still be able to look it up by name
  mat = bpy.data.materials['Material']
  mat.name = 'Material_%d' % mat_count

  # Attach the new material to the active object
  # Make sure it doesn't already have materials
  obj = bpy.context.active_object
  assert len(obj.data.materials) == 0
  obj.data.materials.append(mat)

  # Find the output node of the new material
  output_node = None
  for n in mat.node_tree.nodes:
    if n.name == 'Material Output':
      output_node = n
      break

  # Add a new GroupNode to the node tree of the active material,
  # and copy the node tree from the preloaded node group to the
  # new group node. This copying seems to happen by-value, so
  # we can create multiple materials of the same type without them
  # clobbering each other
  group_node = mat.node_tree.nodes.new('ShaderNodeGroup')
  group_node.node_tree = bpy.data.node_groups[name]

  # Find and set the "Color" input of the new group node
  for inp in group_node.inputs:
    if inp.name in properties:
      inp.default_value = properties[inp.name]

  # Wire the output of the new group node to the input of
  # the MaterialOutput node
  mat.node_tree.links.new(
      group_node.outputs['Shader'],
      output_node.inputs['Surface'],
  )

