#!/usr/bin/env python3
"""Headless OAK-D Lite capture and conservative CPU RGB-D TSDF fusion."""
import argparse
import json
import time
from pathlib import Path
import os
import platform
if platform.machine() == 'aarch64':
    os.environ.setdefault('OPENBLAS_CORETYPE', 'ARMV8')
    os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import numpy as np


def matched(a, b, tolerance=0.02):
    return abs(a - b) <= tolerance


def camera_to_world(previous, source_to_target):
    # Odometry maps previous-camera points into current-camera coordinates.
    return previous @ np.linalg.inv(source_to_target)


def acceptable(transform, information):
    return (np.isfinite(transform).all() and np.isfinite(information).all()
            and np.linalg.norm(transform[:3, 3]) < 0.20
            and np.arccos(np.clip((np.trace(transform[:3, :3])-1)/2, -1, 1)) < 0.35
            and np.linalg.det(transform[:3, :3]) > 0.99)


def capture(args):
    import depthai as dai
    import cv2
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    pipeline = dai.Pipeline()
    rgb = pipeline.create(dai.node.ColorCamera)
    rgb.setBoardSocket(dai.CameraBoardSocket.RGB)
    rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    rgb.setIspScale(1, 3)  # Full 16:9 field of view, 640 x 360, no preview crop.
    rgb.setFps(10)
    mono = []
    for socket in (dai.CameraBoardSocket.LEFT, dai.CameraBoardSocket.RIGHT):
        camera = pipeline.create(dai.node.MonoCamera)
        camera.setBoardSocket(socket)
        camera.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
        camera.setFps(10)
        mono.append(camera)
    stereo = pipeline.create(dai.node.StereoDepth)
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
    stereo.setLeftRightCheck(True)
    stereo.setSubpixel(True)
    stereo.setDepthAlign(dai.CameraBoardSocket.RGB)
    stereo.setOutputSize(640, 360)
    mono[0].out.link(stereo.left)
    mono[1].out.link(stereo.right)
    for name, source in (("rgb", rgb.isp), ("depth", stereo.depth)):
        out = pipeline.create(dai.node.XLinkOut)
        out.setStreamName(name)
        source.link(out.input)
    with dai.Device() as device:
        calibration = device.readCalibration()
        lens = calibration.getLensPosition(dai.CameraBoardSocket.RGB)
        if lens is not None and lens > 0:
            rgb.initialControl.setManualFocus(lens)
        k = np.array(calibration.getCameraIntrinsics(dai.CameraBoardSocket.RGB, 640, 360))
        distortion = np.array(calibration.getDistortionCoefficients(dai.CameraBoardSocket.RGB))
        mx, my = cv2.initUndistortRectifyMap(k, distortion, None, k, (640, 360), cv2.CV_32FC1)
        metadata = {"intrinsics": k.tolist(), "width": 640, "height": 360,
                    "depth_scale": 1000.0, "depth_units": "millimetres",
                    "mxid": device.getMxId(), "depthai": dai.__version__,
                    "rgb_rectified": True, "max_sync_seconds": 0.02, "frames": []}
        (root / "metadata.json").write_text(json.dumps(metadata, indent=2))
        device.startPipeline(pipeline)
        queues = [device.getOutputQueue(n, 4, False) for n in ("rgb", "depth")]
        packets = [None, None]
        start = last = time.monotonic()
        count = 0
        try:
            while count < args.frames:
                if time.monotonic() - last > 30:
                    raise RuntimeError("No usable synchronized RGB-D pair for 30 seconds")
                for i in range(2):
                    if packets[i] is None:
                        packets[i] = queues[i].tryGet()
                if any(p is None for p in packets):
                    time.sleep(0.002)
                    continue
                stamps = [p.getTimestamp().total_seconds() for p in packets]
                if not matched(*stamps):
                    packets[int(stamps[1] < stamps[0])] = None
                    continue
                color = packets[0].getCvFrame()
                depth = packets[1].getFrame()
                packets = [None, None]
                if color.shape != (360, 640, 3) or depth.shape != (360, 640):
                    raise RuntimeError("Unexpected stream sizes; refusing incorrect calibration")
                if np.count_nonzero(depth) < depth.size * 0.05:
                    continue
                color = cv2.remap(color, mx, my, cv2.INTER_LINEAR)[:, :, ::-1].copy()
                if count == 0:
                    edges = cv2.Canny(np.minimum(depth / 12, 255).astype(np.uint8), 30, 80)
                    preview = color[:, :, ::-1].copy()
                    preview[edges > 0] = (0, 255, 0)
                    if not cv2.imwrite(str(root / "alignment.png"), preview):
                        raise RuntimeError("Could not save alignment preview")
                filename = "{:06d}.npz".format(count)
                np.savez_compressed(str(root / filename), color=color, depth=depth)
                metadata["frames"].append({"file": filename, "rgb_time": stamps[0],
                                            "depth_time": stamps[1],
                                            "valid_fraction": float(np.count_nonzero(depth)/depth.size)})
                count += 1
                last = time.monotonic()
                print("Captured {} / {} ({:.1f}s)".format(count, args.frames, last-start), flush=True)
        finally:
            (root / "metadata.json").write_text(json.dumps(metadata, indent=2))
    if count == 0:
        raise RuntimeError("No frames captured")


def reconstruct(args):
    import open3d as o3d
    root = Path(args.input)
    meta = json.loads((root / "metadata.json").read_text())
    k = np.array(meta["intrinsics"])
    intr = o3d.camera.PinholeCameraIntrinsic(meta["width"], meta["height"],
                                          k[0, 0], k[1, 1], k[0, 2], k[1, 2])
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=args.voxel, sdf_trunc=args.voxel*5,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    previous = None
    previous_gray = None
    pose = np.eye(4)
    trajectory = []
    option = o3d.pipelines.odometry.OdometryOption()
    option.max_depth_diff = 0.05
    option.min_depth = args.min_depth
    option.max_depth = args.max_depth
    for index, frame in enumerate(meta["frames"]):
        with np.load(str(root / frame["file"])) as data:
            color = np.ascontiguousarray(data["color"])
            depth = data["depth"].copy()
        depth[(depth < args.min_depth*1000) | (depth > args.max_depth*1000)] = 0
        current = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(color), o3d.geometry.Image(depth),
            depth_scale=meta["depth_scale"], depth_trunc=args.max_depth,
            convert_rgb_to_intensity=False)
        gray = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(color), o3d.geometry.Image(depth),
            depth_scale=meta["depth_scale"], depth_trunc=args.max_depth,
            convert_rgb_to_intensity=True)
        if previous is not None:
            ok, transform, information = o3d.pipelines.odometry.compute_rgbd_odometry(
                previous_gray, gray, intr, np.eye(4),
                o3d.pipelines.odometry.RGBDOdometryJacobianFromHybridTerm(), option)
            if not ok or not acceptable(transform, information):
                raise RuntimeError("Tracking lost at frame {}. Stop and recapture more slowly; no uncertain pose fused.".format(index))
            # Check overlap and geometric consistency independently of the odometry success flag.
            source = o3d.geometry.PointCloud.create_from_rgbd_image(previous, intr).voxel_down_sample(args.voxel*2)
            target = o3d.geometry.PointCloud.create_from_rgbd_image(current, intr).voxel_down_sample(args.voxel*2)
            quality = o3d.pipelines.registration.evaluate_registration(source, target, args.voxel*3, transform)
            if quality.fitness < 0.5 or quality.inlier_rmse > args.voxel*2:
                raise RuntimeError("Insufficient registration quality at frame {}: fitness={} RMSE={}".format(index, quality.fitness, quality.inlier_rmse))
            pose = camera_to_world(pose, transform)
        volume.integrate(current, intr, np.linalg.inv(pose))
        trajectory.append({"file": frame["file"], "camera_to_world": pose.tolist()})
        previous = current
        previous_gray = gray
        print("Integrated {}".format(index+1), flush=True)
    if len(trajectory) < 2:
        raise RuntimeError("Need at least two frames for a scan")
    cloud = volume.extract_point_cloud()
    mesh = volume.extract_triangle_mesh()
    if not len(cloud.points) or not len(mesh.triangles):
        raise RuntimeError("Fusion produced no surface")
    mesh.compute_vertex_normals()
    for name, geometry, writer in (("cloud.ply", cloud, o3d.io.write_point_cloud),
                                   ("mesh.ply", mesh, o3d.io.write_triangle_mesh),
                                   ("mesh.obj", mesh, o3d.io.write_triangle_mesh)):
        if not writer(str(root / name), geometry):
            raise RuntimeError("Export failed: " + name)
    (root / "trajectory.json").write_text(json.dumps(trajectory, indent=2))
    print("Exported {} points, {} triangles; units: metres".format(len(cloud.points), len(mesh.triangles)))


def doctor(args):
    import platform
    import depthai as dai
    import open3d as o3d
    print("OS:", platform.platform(), "architecture:", platform.machine())
    print("DepthAI:", dai.__version__, "Open3D:", o3d.__version__)
    devices = dai.Device.getAllAvailableDevices()
    if not devices:
        raise RuntimeError("No OAK device detected. Check USB cable, power, USB3 port and udev permissions")
    with dai.Device(devices[0]) as device:
        print("Device:", device.getMxId(), "USB:", device.getUsbSpeed())
        cameras = device.getConnectedCameras()
        print("Camera sockets:", cameras)
        if len(cameras) < 3:
            raise RuntimeError("Expected RGB and both stereo cameras")
        print("Calibration:", device.readCalibration().getCameraIntrinsics(dai.CameraBoardSocket.RGB, 640, 360))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("doctor")
    cap = commands.add_parser("capture")
    cap.add_argument("output")
    cap.add_argument("--frames", type=int, default=100)
    rec = commands.add_parser("reconstruct")
    rec.add_argument("input")
    rec.add_argument("--voxel", type=float, default=0.01)
    rec.add_argument("--min-depth", type=float, default=0.4)
    rec.add_argument("--max-depth", type=float, default=2.5)
    args = parser.parse_args()
    if args.command == "capture" and args.frames > 0:
        capture(args)
    elif args.command == "reconstruct" and args.voxel > 0 and 0 < args.min_depth < args.max_depth:
        reconstruct(args)
    elif args.command == "doctor":
        doctor(args)
    else:
        parser.error("Choose doctor, capture (positive frames), or reconstruct (valid depth/voxel values)")


if __name__ == "__main__":
    main()
