import bpy
import os
from bpy_extras.io_utils import ExportHelper
from . import fn_nodes
from . import fn_soft
from . import fn_bake

def addImageNode(mat, nam, res, dir, fmt):
    if bpy.data.images.get(nam):
        bpy.data.images.remove(bpy.data.images.get(nam))
    _image                     = bpy.data.images.new(nam, res, res)
    _image.filepath_raw        = os.path.join(os.path.abspath(dir), nam + "." + fmt.lower())
    _image.file_format         = fmt
    _imagenode                 = mat.node_tree.nodes.new(type="ShaderNodeTexImage") if not mat.node_tree.nodes.get("img") else mat.node_tree.nodes.get("img")
    _imagenode.name            = "img"
    _imagenode.select          = True
    mat.node_tree.nodes.active = _imagenode
    _imagenode.image           = _image
    return _imagenode

def bakeWithBlender(mat, nam, res, dir, fmt):
    restore = mat.use_nodes
    engine  = bpy.context.scene.render.engine
    bpy.context.scene.render.engine="BLENDER_RENDER"
    if bpy.data.images.get(nam):
        bpy.data.images.remove(bpy.data.images.get(nam))
    image = bpy.data.images.new(nam, res, res)
    image.filepath_raw = os.path.join(os.path.abspath(dir), nam + "." + fmt.lower())
    image.file_format  = fmt
    tex = bpy.data.textures.new( nam, type = 'IMAGE')
    tex.image = image
    mat.use_nodes = False
    mtex = mat.texture_slots.add()
    mtex.texture = tex
    mtex.texture_coords = 'UV'
    bpy.context.scene.render.use_bake_selected_to_active = True
    bpy.ops.object.editmode_toggle()
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.data.screens['UV Editing'].areas[1].spaces[0].image = image
    bpy.context.object.active_material.use_textures[0] = False
    bpy.context.scene.render.bake_type = "NORMALS"
    bpy.ops.object.bake_image()
    image.save()
    bpy.ops.object.editmode_toggle()
    mat.use_nodes = restore
    bpy.context.scene.render.engine=engine

class bake_cycles_textures(bpy.types.Operator, ExportHelper):
    bl_idname = "bakemyscan.bake_textures"
    bl_label  = "Textures to textures"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext=''
    use_filter=True
    use_filter_folder=True

    filepath  = bpy.props.StringProperty(
        name="File Path",
        description="Filepath used for exporting the file",
        maxlen=1024,
        subtype='DIR_PATH',
        default="")


    resolution     = bpy.props.IntProperty( name="resolution",     description="image resolution", default=1024, min=128, max=8192)
    imgFormat      = bpy.props.EnumProperty(items= ( ('PNG', 'PNG', 'PNG'), ("JPEG", "JPEG", "JPEG")) , name="imgFormat", description="image format", default="JPEG")
    cageRatio      = bpy.props.FloatProperty(name="cageRatio", description="baking cage size as a ratio", default=0.1, min=0.00001, max=5)
    bake_albedo    = bpy.props.BoolProperty(name="bake_albedo",    description="albedo", default=True)
    bake_geometry  = bpy.props.BoolProperty(name="bake_geometry",   description="geometric normals", default=False)
    bake_surface   = bpy.props.BoolProperty(name="bake_surface",   description="material normals", default=False)
    bake_metallic  = bpy.props.BoolProperty(name="bake_metallic",  description="metalness", default=False)
    bake_roughness = bpy.props.BoolProperty(name="bake_roughness", description="roughness", default=False)
    bake_emission  = bpy.props.BoolProperty(name="bake_emission", description="emission", default=False)
    bake_opacity   = bpy.props.BoolProperty(name="bake_opacity",   description="opacity", default=False)

    @classmethod
    def poll(self, context):
        #Render engine must be cycles
        if bpy.context.scene.render.engine!="CYCLES":
            return 0
        #If more than two objects are selected
        if len(context.selected_objects)>2:
            return 0
        #If no object is active
        if context.active_object is None:
            return 0
        #If something other than a MESH is selected
        for o in context.selected_objects:
            if o.type != "MESH":
                return 0
        #The source object must have correct materials
        source = [o for o in context.selected_objects if o!=context.active_object][0] if len(context.selected_objects)==2 else context.active_object
        target = context.active_object
        #Each material must be not None and have nodes
        if source.active_material is None:
            return 0
        if source.active_material.use_nodes == False:
            return 0
        if context.mode!="OBJECT":
            return 0
        #The target object must have a UV layout
        if len(target.data.uv_layers) == 0:
            return 0
        return 1

    def execute(self, context):
        #Get the directory to save the images to
        print(self.filepath)
        if os.path.exists(self.filepath):
            if os.path.isdir(self.filepath):
                self.directory = os.path.abspath(self.filepath)
            else:
                self.directory = os.path.abspath(os.path.dirname(self.filepath))
        else:
            self.directory = os.path.abspath(os.path.dirname(self.filepath))

        #Find which object is the source and which is the target
        source, target = None, None
        if len(context.selected_objects) == 1:
            source = target = context.selected_objects[0]
        if len(context.selected_objects) == 2:
            target = [o for o in context.selected_objects if o==context.active_object][0]
            source = [o for o in context.selected_objects if o!=target][0]

        #Get the source material
        material  = source.active_material

        # Set the baking parameters
        bpy.data.scenes["Scene"].render.bake.use_selected_to_active = True
        bpy.data.scenes["Scene"].cycles.bake_type = 'EMIT'
        bpy.data.scenes["Scene"].cycles.samples   = 1
        bpy.data.scenes["Scene"].render.bake.margin = 8
        dims = source.dimensions
        bpy.data.scenes["Scene"].render.bake.use_cage = True
        bpy.data.scenes["Scene"].render.bake.cage_extrusion = self.cageRatio * max(max(dims[0], dims[1]), dims[2])
        bpy.data.scenes["Scene"].render.bake.use_clear = True

        #Proceed to the different channels baking
        toBake = {
            "Base Color": self.bake_albedo,
            "Metallic": self.bake_metallic,
            "Roughness": self.bake_roughness,
            "Normal": self.bake_surface,
            "Emission": self.bake_emission,
            "Opacity": self.bake_opacity
        }

        #Bake the Principled shader slots by transforming them to temporary emission shaders
        for baketype in toBake:
            if toBake[baketype]:

                #Copy the active material, and assign it to the source
                tmpMat      = fn_bake.create_source_baking_material(material, baketype)
                tmpMat.name = material.name + "_" + baketype
                source.active_material = tmpMat

                #Create a material for the target
                targetMat = fn_bake.create_target_baking_material(target)

                #Add an image node to the material with the baked result image assigned
                suffix   = baketype.replace(" ", "").lower()
                imgNode  = addImageNode(targetMat, "baked_" + suffix, self.resolution, self.directory, self.imgFormat)

                #Do the baking and save the image
                bpy.ops.object.bake(type="EMIT")
                imgNode.image.save()

                #Remove the material and reassign the original one
                targetMat.node_tree.nodes.remove(imgNode)
                source.active_material = material
                bpy.data.materials.remove(tmpMat)

        #Bake the geometric normals with blender render
        if source != target and self.bake_geometry:

            #Bake the normals with blender
            D    = os.path.abspath(self.directory)
            GEOM = os.path.join(D, "baked_geometry." + self.imgFormat.lower())
            NORM = os.path.join(D, "baked_normal."   + self.imgFormat.lower())
            TMP  = os.path.join(D, "baked_tmp."      + self.imgFormat.lower())
            OUT  = os.path.join(D, "baked_normals."  + self.imgFormat.lower())
            bakeWithBlender(targetMat, "baked_geometry", self.resolution, D, self.imgFormat)

            #Merging the normal maps with Imagemagick
            if self.bake_surface:
                new = fn_bake.overlay_normals(bpy.data.images.load(GEOM), bpy.data.images.load(NORM))
                new.file_format = self.imgFormat
                new.filepath_raw = OUT
                new.save()
            else:
                os.rename(GEOM, OUT)

        # Import the resulting material
        def getbaked(baketype):
            return os.path.join(self.directory, "baked_" + baketype.replace(" ", "").lower() + "." + self.imgFormat.lower())

        importSettings = {
            "albedo":    getbaked("Base Color") if self.bake_albedo else None,
            "metallic":  getbaked("Metallic")   if self.bake_metallic else None,
            "roughness": getbaked("Roughness")  if self.bake_roughness else None,
            "normal":    getbaked("Normals")    if self.bake_geometry or self.bake_surface else None,
            "emission":  getbaked("Emission")   if self.bake_emission else None,
            "opacity":   getbaked("Opacity")    if self.bake_opacity else None
        }

        #Init the material
        for o in context.selected_objects:
            if o!=context.active_object:
                o.select=False
        bpy.ops.bakemyscan.create_empty_material(name="baking_" + context.active_object.name)
        for _type in importSettings:
            if importSettings[_type] is not None:
                bpy.ops.bakemyscan.assign_texture(slot=_type, filepath=importSettings[_type])

        return{'FINISHED'}

def register() :
    bpy.utils.register_class(bake_cycles_textures)

def unregister() :
    bpy.utils.unregister_class(bake_cycles_textures)
