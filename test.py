import bpy, _cycles
print(_cycles.available_devices())
bpy.context.user_preferences.system.compute_device = 'BLABLABLA'
