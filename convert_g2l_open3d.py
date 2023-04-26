import os
import open3d as o3d
import numpy as np
from scipy.spatial.transform import Rotation
from argparse import ArgumentParser
from PIL import Image
import skvideo.io
import shutil

description = """
This script visualizes datasets collected using the Stray Scanner app.
"""

usage = """
Basic usage: python stray_visualize.py <path-to-dataset-folder>
"""

DEPTH_WIDTH = 256
DEPTH_HEIGHT = 192
MAX_DEPTH = 20.0

def read_args():
    parser = ArgumentParser(description=description, usage=usage)
    parser.add_argument('path', type=str, help="Path to StrayScanner dataset to process.")
    parser.add_argument('--trajectory', '-t', action='store_true', help="Visualize the trajectory of the camera as a line.")
    parser.add_argument('--frames', '-f', action='store_true', help="Visualize camera coordinate frames from the odometry file.")
    parser.add_argument('--point-clouds', '-p', action='store_true', help="Show concatenated point clouds.")
    parser.add_argument('--integrate', '-i', action='store_true', help="Integrate point clouds using the Open3D RGB-D integration pipeline, and visualize it.")
    parser.add_argument('--mesh-filename', type=str, help='Mesh generated from point cloud integration will be stored in this file. open3d.io.write_triangle_mesh will be used.', default=None)
    parser.add_argument('--every', type=int, default=60, help="Show only every nth point cloud and coordinate frames. Only used for point cloud and odometry visualization.")
    parser.add_argument('--voxel-size', type=float, default=0.015, help="Voxel size in meters to use in RGB-D integration.")
    parser.add_argument('--confidence', '-c', type=int, default=1,
            help="Keep only depth estimates with confidence equal or higher to the given value. There are three different levels: 0, 1 and 2. Higher is more confident.")
    return parser.parse_args()

def _resize_camera_matrix(camera_matrix, scale_x, scale_y):
    fx = camera_matrix[0, 0]
    fy = camera_matrix[1, 1]
    cx = camera_matrix[0, 2]
    cy = camera_matrix[1, 2]
    return np.array([[fx * scale_x, 0.0, cx * scale_x],
        [0., fy * scale_y, cy * scale_y],
        [0., 0., 1.0]])

def read_data(flags):
    # intrinsics = np.loadtxt(os.path.join(flags.path, 'camera_matrix.csv'), delimiter=',')
    odometry = np.loadtxt(os.path.join(flags.path, 'odometry.csv'), delimiter=',', skiprows=1)
    extrinsiccsv = np.loadtxt(os.path.join(flags.path, 'extrinsic.csv'), delimiter=',',skiprows=0)
    intrinsicscsv = np.loadtxt(os.path.join(flags.path, "intrinsic.csv"), delimiter=',', skiprows=0)
    poses = []
    extrinsics = []
    intrinsics = []

    for line in odometry:
        # timestamp, frame, x, y, z, qx, qy, qz, qw
        position = line[2:5]
        quaternion = line[5:]
        T_WC = np.eye(4)
        T_WC[:3, :3] = Rotation.from_quat(quaternion).as_matrix()
        T_WC[:3, 3] = position
        poses.append(T_WC)
    i = 0
    for line in extrinsiccsv:
        # x,y,z,r00,r01,r02,r10,r11,r12,r20,r21,r22
        ex_m = np.array([line[3], line[4], line[5], line[0], line[6], line[7], line[8], line[1], line[9], line[10], line[11], line[2], 0.0, 0.0, 0.0, 1.0]).reshape((4,4))
        extrinsics.append(ex_m)

        g2lcam = str(line[0]) + " " + str(line[1]) + " " + str(line[2]) + " " + str(line[3]) + " " + str(line[4]) + " " + str(line[5]) + " " \
              + str(line[6]) + " " + str(line[7]) + " " + str(line[8]) + " " + str(line[9]) + " " + str(line[10]) + " " + str(line[11]) + "\n"
        camfile = open(f'/Users/hoangle/Documents/14_2_1/sam1/mvs/color_{i:04}.cam', 'w')
        camfile.write(g2lcam)
        i += 1
    i = 0
    for line in intrinsicscsv:
        # r00,r01,r02, r10,r11,r12, r20,r21,r22
        in_m = np.array([line[0], line[1], line[2], line[3], line[4], line[5], line[6], line[7], line[8]]).reshape((3,3))
        intrinsics.append(in_m)
        
        g2lcam = str(line[0]/1920.0) + " " + "0.0" + " " + "0.0" + " " + "1.0" + " " + "0.5" + " " + "0.5" + "\n" 
        camfile = open(f'/Users/hoangle/Documents/14_2_1/sam1/mvs/color_{i:04}.cam', 'a')
        camfile.write(g2lcam)
        i += 1
    i = 0

    depth_dir = os.path.join(flags.path, 'depth')
    depth_frames = [os.path.join(depth_dir, p) for p in sorted(os.listdir(depth_dir))]
    depth_frames = [f for f in depth_frames if '.npy' in f or '.png' in f]

    rgb_dir = os.path.join(flags.path, 'rgb')
    rgb_frames = [os.path.join(rgb_dir, p) for p in sorted(os.listdir(rgb_dir))]
    rgb_frames = [f for f in rgb_frames if '.npy' in f or '.jpeg' in f]
    print("len: ", len(poses), len(depth_frames), len(rgb_frames), len(extrinsics), len(intrinsics))
    # print("intrinsic: ", intrinsics)
    return { 'poses': poses, 'depth_frames': depth_frames, 'rgb_frames': rgb_frames, 'extrinsics': extrinsics, 'intrinsics': intrinsics }

def load_depth(path, confidence=None, filter_level=0):
    if path[-4:] == '.npy':
        depth_mm = np.load(path)
    elif path[-4:] == '.png':
        depth_mm = np.array(Image.open(path))
    depth_m = depth_mm.astype(np.float32) / 1000.0
    if confidence is not None:
        depth_m[confidence < filter_level] = 0.0
    return o3d.geometry.Image(depth_m)

def load_rgb(path):
    rgb_mm = np.array(Image.open(path))
    rgb = Image.fromarray(rgb_mm)
    rgb = rgb.resize((DEPTH_WIDTH, DEPTH_HEIGHT))
    # rgb_m = rgb_mm.resize(DEPTH_WIDTH, DEPTH_HEIGHT)
    # print("rgb_mm: ", type(rgb_mm), rgb_mm.shape)
    # rgb_m = rgb_mm.astype(np.float32) / 1000.0
    rgb = np.array(rgb)
    return rgb

def load_confidence(path):
    return np.array(Image.open(path))

def get_intrinsics(intrinsics):
    """
    Scales the intrinsics matrix to be of the appropriate scale for the depth maps.
    """
    intrinsics_scaled = _resize_camera_matrix(intrinsics, DEPTH_WIDTH / 1920, DEPTH_HEIGHT / 1440)
    return o3d.camera.PinholeCameraIntrinsic(width=DEPTH_WIDTH, height=DEPTH_HEIGHT, fx=intrinsics_scaled[0, 0],
        fy=intrinsics_scaled[1, 1], cx=intrinsics_scaled[0, 2], cy=intrinsics_scaled[1, 2])

def trajectory(flags, data):
    """
    Returns a set of lines connecting each camera poses world frame position.
    returns: [open3d.geometry.LineSet]
    """
    line_sets = []
    previous_pose = None
    for i, T_WC in enumerate(data['poses']):
        if previous_pose is not None:
            points = o3d.utility.Vector3dVector([previous_pose[:3, 3], T_WC[:3, 3]])
            lines = o3d.utility.Vector2iVector([[0, 1]])
            line = o3d.geometry.LineSet(points=points, lines=lines)
            line_sets.append(line)
        previous_pose = T_WC
    return line_sets

def show_frames(flags, data):
    """
    Returns a list of meshes of coordinate axes that have been transformed to represent the camera matrix
    at each --every:th frame.

    flags: Command line arguments
    data: dict with keys ['poses', 'intrinsics']
    returns: [open3d.geometry.TriangleMesh]
    """
    frames = [o3d.geometry.TriangleMesh.create_coordinate_frame().scale(0.25, np.zeros(3))]
    for i, T_WC in enumerate(data['poses']):
        if not i % flags.every == 0:
            continue
        # print(f"Frame {i}", end="\r")
        mesh = o3d.geometry.TriangleMesh.create_coordinate_frame().scale(0.1, np.zeros(3))
        frames.append(mesh.transform(T_WC))
    return frames

def point_clouds(flags, data):
    """
    Converts depth maps to point clouds and merges them all into one global point cloud.
    flags: command line arguments
    data: dict with keys ['intrinsics', 'poses']
    returns: [open3d.geometry.PointCloud]
    """
    pcs = []
    # intrinsics = get_intrinsics(data['intrinsics'])
    pc = o3d.geometry.PointCloud()
    meshes = []
    for i, (T_WC) in enumerate(zip(data['poses'])):
        T_CW = np.linalg.inv(T_WC)
        # print(data['extrinsics'][i])
        # print("T_CW: ", i, "\n", T_CW[0])
        # if i % flags.every != 0:
        #     continue
        # print(f"Point cloud {i}", end="\r")
        # T_CW = np.linalg.inv(T_WC)
        
        confidence = load_confidence(os.path.join(flags.path, 'confidence', f'{(i+9):06}.png'))
        depth_path = data['depth_frames'][i]
        rgb_path = data['rgb_frames'][i]
        shutil.copy(depth_path, f'/Users/hoangle/Documents/14_2_1/sam1/mvs/depth_{i:04}.png')
        shutil.copy(rgb_path, f'/Users/hoangle/Documents/14_2_1/sam1/mvs/color_{i:04}.jpeg')
        depth = load_depth(depth_path, confidence, filter_level=flags.confidence)
        rgb = load_rgb(rgb_path)
        # return
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(rgb), depth,
            depth_scale=1.0, depth_trunc=MAX_DEPTH, convert_rgb_to_intensity=False)
        pc += o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, get_intrinsics(data['intrinsics'][i]), extrinsic=data['extrinsics'][i])
    return [pc]

def integrate(flags, data):
    """
    Integrates collected RGB-D maps using the Open3D integration pipeline.

    flags: command line arguments
    data: dict with keys ['intrinsics', 'poses']
    Returns: open3d.geometry.TriangleMesh
    """
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
            voxel_length=flags.voxel_size,
            sdf_trunc=0.05,
            color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)

    # intrinsics = get_intrinsics(data['intrinsics'])
    for i, (T_WC) in enumerate(zip(data['poses'])):
        # print(f"Integrating frame {i:06}", end='\r')
        depth_path = data['depth_frames'][i]
        rgb_path = data['rgb_frames'][i]
        depth = load_depth(depth_path)
        # rgb = Image.fromarray(rgb)
        # rgb = rgb.resize((DEPTH_WIDTH, DEPTH_HEIGHT))
        # rgb = np.array(rgb)
        rgb = load_rgb(rgb_path)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(rgb), depth,
            depth_scale=1.0, depth_trunc=MAX_DEPTH, convert_rgb_to_intensity=False)

        volume.integrate(rgbd, get_intrinsics(data['intrinsics'][i]), np.linalg.inv(T_WC[0]))
    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    return mesh


def validate(flags):
    # if not os.path.exists(os.path.join(flags.path, 'rgb.mp4')):
    #     absolute_path = os.path.abspath(flags.path)
    #     print(f"The directory {absolute_path} does not appear to be a directory created by the Stray Scanner app.")
    #     return False
    return True

def main():
    flags = read_args()

    if not validate(flags):
        return

    if not flags.frames and not flags.point_clouds and not flags.integrate:
        flags.frames = True
        flags.point_clouds = True
        flags.trajectory = True

    data = read_data(flags)
    geometries = []
    if flags.trajectory:
        geometries += trajectory(flags, data)
    if flags.frames:
        geometries += show_frames(flags, data)
    if flags.point_clouds:
        geometries += point_clouds(flags, data)
    if flags.integrate:
        mesh = integrate(flags, data)
        if flags.mesh_filename is not None:
            o3d.io.write_triangle_mesh(flags.mesh_filename, mesh)
        geometries += [mesh]
    o3d.visualization.draw_geometries(geometries)

if __name__ == "__main__":
    main()

