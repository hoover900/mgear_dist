"""rbf node to normalize the calls across any number of supported
rbf node types. First supported "weightDriver"/ingo clemens/Brave Rabit

Attributes:
    CTL_SUFFIX (str): name of the control suffixe
    DRIVEN_SUFFIX (str): suffix to be applied to driven group
    DRIVER_CTL_ATTR_NAME (str): name of the attribute to store driver control
    DRIVER_POSEINPUT_ATTR (str): name of attr to store control driver(holder)
    DRIVER_POSES_ATTR (str): name of attr to store control
    GENERIC_SUFFIX (str): generic suffix if one not provided by support module
    RBF_SCALE_ATTR (str): name of attr applied to driven control
    RBF_SETUP_ATTR (str): name of attr to store setup name for group of rbf
    ROTATE_ATTRS (list): convenience list of transform attrs
    SCALE_ATTRS (list): convenience list of transform attrs
    SUPPORTED_RBF_NODES (tuple): currently supported rbf node types
    TRANSFORM_SUFFIX (str): suffix of transform nodes for rbf nodes
    TRANSLATE_ATTRS (list): convenience list of transform attrs

TODO - refactor as more supported rbf node types are added

"""
# python
import math

# maya
import maya.cmds as mc
import pymel.core as pm
import maya.OpenMaya as OpenMaya

# mgear
from mgear.maya import transform

# =============================================================================
# constants
# =============================================================================

DRIVEN_SUFFIX = "_driven"
CTL_SUFFIX = "_ctl"
TRANSFORM_SUFFIX = "_trfm"

RBF_SETUP_ATTR = "rbf_setup_name"

TRANSLATE_ATTRS = ["translateX",
                   "translateY",
                   "translateZ"]

ROTATE_ATTRS = ["rotateX",
                "rotateY",
                "rotateZ"]

SCALE_ATTRS = ["scaleX",
               "scaleY",
               "scaleZ"]

SUPPORTED_RBF_NODES = ("weightDriver",)

GENERIC_SUFFIX = "_RBF"

DRIVER_CTL_ATTR_NAME = "driverControlName"
DRIVER_POSES_ATTR = "driverPoses"
DRIVER_POSEINPUT_ATTR = "poseInput"

RBF_SCALE_ATTR = "RBF_Multiplier"


# =============================================================================
# general functions
# =============================================================================
def addDrivenGroup(node):
    """add driven group, pad, above the provided node for direct connection

    Args:
        node (str): name of node to add group above

    Returns:
        str: of node created
    """
    parentOfTarget = mc.listRelatives(node, p=True) or None
    if not parentOfTarget:
        return node
    if node.endswith(CTL_SUFFIX):
        drivenName = node.replace(CTL_SUFFIX, DRIVEN_SUFFIX)
    else:
        drivenName = "{}{}".format(DRIVEN_SUFFIX)
    drivenName = mc.group(name=drivenName, p=parentOfTarget[0], em=True)
    mc.parent(node, drivenName)
    return drivenName


def removeDrivenGroup(node):
    """remove driven group above desired node

    Args:
        node (str): name of node to check
    """
    parentOfTarget = mc.listRelatives(node, p=True) or None
    childrenNode = mc.listRelatives(node, type="transform")

    for child in childrenNode:
        if parentOfTarget is None:
            mc.parent(child, w=True)
        else:
            mc.parent(child, parentOfTarget[0])
    mc.delete(node)


def decompMatrix(node, matrix):
    '''
    Decomposes a MMatrix in new api. Returns an list of
    translation,rotation,scale in world space.

    Args:
        node (str): name of node to query rotate order
        matrix (MMatrix): mmatrix to decompos

    Returns:
        TYPE: Description
    '''
    # Rotate order of object
    rotOrder = mc.getAttr("{}.rotateOrder".format(node))

    # Puts matrix into transformation matrix
    mTransformMtx = OpenMaya.MTransformationMatrix(matrix)

    # Translation Values
    trans = mTransformMtx.translation(OpenMaya.MSpace.kObject)

    # Euler rotation value in radians
    eulerRot = mTransformMtx.eulerRotation()

    # Reorder rotation order based on ctrl.
    eulerRot.reorderIt(rotOrder)

    radian = 180.0 / math.pi

    rotations = [rot * radian for rot in [eulerRot.x, eulerRot.y, eulerRot.z]]

    # Find world scale of our object.
    # for scale we need to utilize MScriptUtil to deal with the native
    # double pointers
    scaleUtil = OpenMaya.MScriptUtil()
    scaleUtil.createFromList([0, 0, 0], 3)
    scaleVec = scaleUtil.asDoublePtr()
    mTransformMtx.getScale(scaleVec, OpenMaya.MSpace.kObject)
    scale = [OpenMaya.MScriptUtil.getDoubleArrayItem(scaleVec, i)
             for i in range(0, 3)]

    # Return Values
    return [trans.x, trans.y, trans.z], rotations, scale


def resetDrivenNodes(node):
    """use mgear convenience function to reset all available transform nodes

    Args:
        node (str): node to reset
    """
    children = mc.listRelatives(node, type="transform")
    controlNode = node.replace(DRIVEN_SUFFIX, CTL_SUFFIX)
    if mc.objExists(controlNode) and controlNode in children:
        transform.resetTransform(pm.PyNode(controlNode))
    transform.resetTransform(pm.PyNode(node))


def getDrivenMatrix(node):
    """check if there is a control node for the provided node(driven)
    if so, collect the matrix information for both

    Args:
        node (pynode): driven group/driven node

    Returns:
        MMatrix: of total position including the control
    """
    children = mc.listRelatives(node, type="transform")
    node = pm.PyNode(node)
    controlNode = node.replace(DRIVEN_SUFFIX, CTL_SUFFIX)
    if mc.objExists(controlNode) and controlNode in children:
        controlNode = pm.PyNode(controlNode)
        nodeInverParMat = node.getAttr("parentInverseMatrix")
        controlMat = controlNode.getMatrix(worldSpace=True)
        defaultMat = OpenMaya.MMatrix()
        if controlMat == defaultMat:
            totalMatrix = defaultMat
        else:
            totalMatrix = controlMat * nodeInverParMat
    else:
        totalMatrix = node.getMatrix(worldSpace=False)

    return totalMatrix


def createRBFToggleAttr(node):
    """creates a node to toggle the rbf pose that drives the node

    Args:
        node (str): desired node to be tagged with attr
    """
    try:
        mc.addAttr(node,
                   ln=RBF_SCALE_ATTR,
                   at="float",
                   dv=1,
                   min=0,
                   max=1,
                   k=True)
    except RuntimeError:
        pass


def connectRBFToggleAttr(node, rbfNode, rbfEnableAttr):
    """connect the "envelope" attr with its corresponding rbfNode

    Args:
        node (str): node with attr
        rbfNode (str): rbf node with receiving attr
        rbfEnableAttr (str): targeted rbf node for disabling node
    """
    nodeAttr = "{}.{}".format(node, RBF_SCALE_ATTR)
    rbfAttr = "{}.{}".format(rbfNode, rbfEnableAttr)
    mc.connectAttr(nodeAttr, rbfAttr, f=True)


def deleteRBFToggleAttr(node):
    """remove the toggle attribute from the node

    Args:
        node (str): node to remove toggle attr from
    """
    try:
        mc.deleteAttr("{}.{}".format(node, RBF_SCALE_ATTR))
    except ValueError:
        pass


def getConnectedRBFToggleNode(node, toggleAttr):
    """get the node connected to the rbf(node)

    Args:
        node (str): rbf node
        toggleAttr (str): envelope attr to check

    Returns:
        str: connected node
    """
    rbfAttr = "{}.{}".format(node, toggleAttr)
    driverControl = mc.listConnections(rbfAttr)
    if driverControl:
        return driverControl[0]
    return driverControl


def createDriverControlAttr(node):
    """create the string attr where information will be stored for query
    associated driver anim control

    Args:
        node (str): rbf node to tag with information
    """
    try:
        mc.addAttr(node, ln=DRIVER_CTL_ATTR_NAME, dt="string")
    except RuntimeError:
        pass


def getDriverControlAttr(node):
    """get the stored information from control attr

    Args:
        node (str): name of rbfNode

    Returns:
        str: contents of attr, animControl
    """
    try:
        return mc.getAttr("{}.{}".format(node, DRIVER_CTL_ATTR_NAME))
    except ValueError:
        return ""


def setDriverControlAttr(node, controlName):
    """set attr with the driver animControl string

    Args:
        node (str): name of rbfnode
        controlName (str): name of animControl(usually)
    """
    if not mc.attributeQuery(DRIVER_CTL_ATTR_NAME, n=node, ex=True):
        createDriverControlAttr(node)
    mc.setAttr("{}.{}".format(node, DRIVER_CTL_ATTR_NAME),
               controlName,
               type="string")


def getSceneRBFNodes():
    """get all rbf nodes in the scene of supported type

    Returns:
        list: of rbf nodes, see supported types
    """
    return mc.ls(type=SUPPORTED_RBF_NODES) or []


def getSceneSetupNodes():
    """get rbf nodes with setups attributes

    Returns:
        list: of rbf nodes with setup information
    """
    nodes = set(mc.ls(type=SUPPORTED_RBF_NODES))
    return [rbf for rbf in nodes if mc.attributeQuery(RBF_SETUP_ATTR,
                                                      n=rbf,
                                                      ex=True)]


def getRbfSceneSetupsInfo(includeEmpty=True):
    """gather scene rbf nodes with setups in dict

    Args:
        includeEmpty (bool, optional): should rbf nodes with empty setup names
        be included

    Returns:
        dict: setupName(str):list associated rbf nodes
    """
    setups_dict = {"empty": []}
    for rbfNode in getSceneSetupNodes():
        setupName = mc.getAttr("{}.{}".format(rbfNode, RBF_SETUP_ATTR))
        if setupName == "":
            setups_dict["empty"].append(rbfNode)
            continue
        if setupName in setups_dict:
            setups_dict[setupName].append(rbfNode)
        else:
            setups_dict[setupName] = [rbfNode]
    if not includeEmpty:
        setups_dict.pop("empty")
    return setups_dict


def setSetupName(node, setupName):
    """set setup name on the specified node

    Args:
        node (str): name of rbf node to set
        setupName (str): name of setup
    """
    if not mc.attributeQuery(RBF_SETUP_ATTR, n=node, ex=True):
        mc.addAttr(node, ln=RBF_SETUP_ATTR, dt="string")
    mc.setAttr("{}.{}".format(node, RBF_SETUP_ATTR), setupName, type="string")


def getSetupName(node):
    """get setup name from specified rbf node

    Args:
        node (str): name of rbf node

    Returns:
        str: name of setup associated with node
    """
    if not mc.attributeQuery(RBF_SETUP_ATTR, n=node, ex=True):
        return None
    return mc.getAttr("{}.{}".format(node, RBF_SETUP_ATTR))


class RBFNode(object):
    """A class to normalize the function between different types of rbf nodes
    that essentially perform the same task. Look to weightNode_io for examples
    of normalized function calls to specific nodeType information with this
    class.

    Attributes:
        name (str): name of the node that either exists or to be created
        rbfType (str): nodeType to create node of supported type
        transformNode (str): name of transform node
    """

    def __init__(self, name):
        self.name = name
        self.transformNode = None
        if mc.objExists(name) and mc.nodeType(name) in SUPPORTED_RBF_NODES:
            self.rbfType = mc.nodeType(name)
            self.transformNode = self.getTransformParent()
            self.lengthenCompoundAttrs()
        else:
            self.create()
            createDriverControlAttr(self.name)

    def __repr__(self):
        """overwritten so that the RBFNode instance can be treated as a pymal
        node. Convenience

        Returns:
            str: name of rbfNode node correctly formated
        """
        return self.name

    def __unicode__(self):
        """overwritten so that the RBFNode instance can be treated as a pymal
        node. Convenience

        Returns:
            str: name of rbfNode node correctly formated
        """
        return unicode(self.name).encode('utf-8')

    def __str__(self):
        """overwritten so that the RBFNode instance can be treated as a pymal
        node. Convenience

        Returns:
            str: name of rbfNode node correctly formated
        """
        return str(self.name)

    def nodeType_suffix(self):
        """optional override with a module/node specific suffix for naming
        """
        self.nodeType_suffix = GENERIC_SUFFIX

    def formatName(self):
        """standardized the naming of all rbf nodes for consistency

        Returns:
            str: name of all supported rbf nodes
        """
        return "{}{}".format(self.name, self.nodeType_suffix())

    def create(self):
        """create an RBF node of type, defined by the subclassed module

        Raises:
            NotImplementedError: Description
        """
        raise NotImplementedError()

    def getPoseInfo(self):
        """get poseInfo dict

        Raises:
            NotImplementedError: each rbf node is unique, adhere here for
            rbf manager ui support
        """
        raise NotImplementedError()

    def getNodeInfo(self):
        """get all the info for for the node in the form of a dict

        Raises:
            NotImplementedError: NotImplementedError: each rbf node is unique,
            adhere here for rbf manager ui support
        """
        raise NotImplementedError()

    def lengthenCompoundAttrs(self):
        """convenience function, sanity check for zero'd compound attrs
        """
        pass

    def addPose(self, poseInput, poseValue, posesIndex=None):
        """add pose to the weightDriver node provided. Also used for editing
        an existing pose, since you can specify the index. If non provided
        assume new

        Args:
            node (str): weightedDriver
            poseInput (list): list of the poseInput values
            poseValue (list): of poseValue values
            posesIndex (int, optional): at desired index, if none assume
            latest/new
        """
        raise NotImplementedError()

    def deletePose(self, indexToPop):
        """gather information on node, remove desired index and reapply

        Args:
            node (str): weightDriver
            indexToPop (int): pose index to remove
        """
        raise NotImplementedError()

    def getDriverNode(self):
        """get nodes that are driving weightDriver node

        Returns:
            list: of driver nodes
        """
        raise NotImplementedError()

    def getDriverNodeAttributes(self):
        """get the connected attributes of the provided compound attr in order
        of index - Sanity check

        Returns:
            list: of connected attrs in order
        """
        raise NotImplementedError()

    def getDrivenNode(self):
        """get driven nodes connected to weightDriver

        Returns:
            list: of driven nodes
        """
        raise NotImplementedError()

    def getDrivenNodeAttributes(self):
        """get the connected attributes of the provided compound attr in order
        of index - Sanity check

        Returns:
            list: of connected attrs in order
        """
        raise NotImplementedError()

    def getSetupName(self):
        return getSetupName(self.name)

    def setSetupName(self, setupName):
        setSetupName(str(self.name), setupName)

    def setDriverNode(self, driverNode, driverAttrs):
        """set the node that will be driving the evaluation on our poses

        Args:
            node (str): name of weightDriver node
            driverNode (str): name of driver node
            driverAttrs (list): of attributes used to perform evaluations
        """
        raise NotImplementedError()

    def setDrivenNode(self, drivenNode, drivenAttrs, parent=True):
        """set the node to be driven by the weightDriver

        Args:
            node (str): weightDriver node
            drivenNode (str): name of node to be driven
            drivenAttrs (list): of attributes to be driven by weightDriver
        """
        raise NotImplementedError()

    def getTransformParent(self):
        """get a dict of all the information to be serialized to/from json

        Returns:
            dict: information to be recreated on import
        """
        NotImplementedError()

    def copyPoses(self, nodeB, emptyPoseValues=True):
        """Copy poses from nodeA to nodeB with the option to be blank or node
        for syncing nodes

        Args:
            nodeB (str): name of weightedNode
            emptyPoseValues (bool, optional): should the copy just be the same
            number of poses but blank output value

        Returns:
            n/a: n/a
        """
        NotImplementedError()

    def setDriverControlAttr(self, controlName):
        setDriverControlAttr(self.name, controlName)

    def getDriverControlAttr(self):
        driverControl = getDriverControlAttr(self.name)
        if driverControl == "":
            driverControl = self.getDriverNode()[0]
        return driverControl

    def recallDriverPose(self, poseIndex):
        NotImplementedError()

    def getPoseValues(self, resetDriven=True):
        """get all pose values from rbf node

        Args:
            resetDriven (bool, optional): reset driven animControl

        Returns:
            list: of poseValues
        """
        attributeValue_dict = {}
        drivenNode = self.getDrivenNode()[0]
        drivenAttrs = self.getDrivenNodeAttributes()
        (trans,
         rotate,
         scale) = decompMatrix(drivenNode,
                               getDrivenMatrix(drivenNode))
        for attr in drivenAttrs:
            if attr in TRANSLATE_ATTRS:
                index = TRANSLATE_ATTRS.index(attr)
                attributeValue_dict[attr] = trans[index]
            elif attr in ROTATE_ATTRS:
                index = ROTATE_ATTRS.index(attr)
                attributeValue_dict[attr] = rotate[index]
            elif attr in SCALE_ATTRS:
                index = SCALE_ATTRS.index(attr)
                attributeValue_dict[attr] = scale[index]
            else:
                nodePlug = "{}.{}".format(drivenNode, attr)
                attributeValue_dict[attr] = mc.getAttr(nodePlug)
        if resetDriven:
            resetDrivenNodes(drivenNode)
        poseValues = [attributeValue_dict[attr] for attr in drivenAttrs]
        return poseValues

    def forceEvaluation(self):
        """convenience function to force re evaluation on the rbf nodes
        most nodes support this
        """
        NotImplementedError()

    def getRBFToggleAttr(self):
        """get the specific to the type, "envelope" attr for rbf node
        """
        NotImplementedError()
        # return "scale"

    def deleteRBFToggleAttr(self):
        """convenience function to delete the connected "enevelope" from the
        anim control node

        Returns:
            TYPE: Description
        """
        driverControl = getConnectedRBFToggleNode(self.name,
                                                  self.getRBFToggleAttr())
        if not driverControl:
            return
        deleteRBFToggleAttr(driverControl)