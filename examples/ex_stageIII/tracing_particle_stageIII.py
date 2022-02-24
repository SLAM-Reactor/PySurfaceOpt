#!/usr/bin/env python3
from simsopt.field.biotsavart import BiotSavart
from simsopt.field.magneticfieldclasses import InterpolatedField, UniformInterpolationRule
from simsopt.geo.surfacexyztensorfourier import SurfaceXYZTensorFourier
from simsopt.field.coil import coils_via_symmetries
from simsopt.field.tracing import trace_particles_starting_on_surface, SurfaceClassifier, \
    particles_to_vtk, LevelsetStoppingCriterion, plot_poincare_data
from simsopt.geo.curve import curves_to_vtk
from simsopt.util.constants import ALPHA_PARTICLE_MASS, ALPHA_PARTICLE_CHARGE, ONE_EV
import simsoptpp as sopp
import pysurfaceopt as pys
from pysurfaceopt.surfaceobjectives import ToroidalFlux, MajorRadius, BoozerResidual, NonQuasiAxisymmetricRatio, Iotas, Volume, Area, Aspect_ratio

try:
    from mpi4py import MPI
    comm = MPI.COMM_WORLD
except ImportError:
    comm = None

import numpy as np
import time
import os
import logging
import sys
sys.path.append(os.path.join("..", "tests", "geo"))
logging.basicConfig()
logger = logging.getLogger('simsopt.field.tracing')
logger.setLevel(1)

# Directory for output
OUT_DIR = "./output/"
os.makedirs(OUT_DIR, exist_ok=True)


length=18
assert length==18 or length==20 or length==22 or length==24
ts_dict={18:'1639707710.6463501', 20: '1639796640.5101252', 22:'1642522947.7884622', 24:'1642523475.5701194'}
boozer_surface_list, base_curves, base_currents, coils = pys.load_surfaces_in_stageII(mpol=10, ntor=10, stellsym=True, Nt_coils=16, idx_surfaces=[0,2,4], exact=True, length=length, time_stamp=ts_dict[length])
bs_tf_list = [BiotSavart(coils) for bs in boozer_surface_list]
J_toroidal_flux = [ToroidalFlux(boozer_surface, bs_tf) for boozer_surface, bs_tf in zip(boozer_surface_list, bs_tf_list)]
J_aspect_ratio = [Aspect_ratio(boozer_surface.surface) for boozer_surface in boozer_surface_list]
tf_list=[abs(tf.J()) for tf in J_toroidal_flux]
ar_list=[ar.J() for ar in J_aspect_ratio]
#max_tf = max(tf_list)
#print("tf:",tf_list/max_tf)
#print("ar:",ar_list)

print("compute a surface close to the magnetic axis to normalize the field")
boozer_surface_inner = boozer_surface_list[0]
tf_spawn = J_toroidal_flux[0]
iota0=boozer_surface_inner.res['iota']
G0=boozer_surface_inner.res['G']
boozer_surface_inner.targetlabel = 1e-3
boozer_surface_inner.recompute_bell()
tf_spawn.recompute_bell()
res = boozer_surface_inner.solve_residual_equation_exactly_newton(tol=1e-13, maxiter=30,iota=iota0,G=G0)
tf_list=[abs(tf.J()) for tf in J_toroidal_flux]
ar_list=[ar.J() for ar in J_aspect_ratio]
print("tf:",tf_list)
print("ar:",ar_list)

print("compute the 0.25 surface")
# compute the s=0.25 surface
vol_dict={18:-0.14036}
boozer_surface_spawn = boozer_surface_list[1]
tf_spawn = J_toroidal_flux[1]
iota0=boozer_surface_spawn.res['iota']
G0=boozer_surface_spawn.res['G']
boozer_surface_spawn.targetlabel = vol_dict[length]
boozer_surface_spawn.recompute_bell()
tf_spawn.recompute_bell()
res = boozer_surface_spawn.solve_residual_equation_exactly_newton(tol=1e-13, maxiter=30,iota=iota0,G=G0)
tf_list=[abs(tf.J()) for tf in J_toroidal_flux]
ar_list=[ar.J() for ar in J_aspect_ratio]
max_tf = max(tf_list)
print("new max tf",max_tf)
print("tf:",tf_list/max_tf)
print("ar:",ar_list)
boozer_surface_outer=boozer_surface_list[2]

# convert these surfaces to full period surfaces
mpol = 10
ntor = 10
stellsym = True
nfp = 2
phis = np.linspace(0, 1, nfp*2*ntor+1, endpoint=False)
thetas = np.linspace(0, 1, 2*mpol+1, endpoint=False)
s_inner = SurfaceXYZTensorFourier(mpol=mpol, ntor=ntor, stellsym=stellsym, nfp=nfp, quadpoints_phi=phis, quadpoints_theta=thetas)
s_spawn = SurfaceXYZTensorFourier(mpol=mpol, ntor=ntor, stellsym=stellsym, nfp=nfp, quadpoints_phi=phis, quadpoints_theta=thetas)
s_outer = SurfaceXYZTensorFourier(mpol=mpol, ntor=ntor, stellsym=stellsym, nfp=nfp, quadpoints_phi=phis, quadpoints_theta=thetas)

s_inner.x=boozer_surface_inner.surface.x*1.7
s_spawn.x=boozer_surface_spawn.surface.x*1.7
s_outer.x=boozer_surface_outer.surface.x*1.7

s_inner.to_vtk(OUT_DIR+"inner_surface")
s_spawn.to_vtk(OUT_DIR+"spawn_surface")
s_outer.to_vtk(OUT_DIR+"outer_surface")




print("Running 1_Simple/tracing_particle.py")
print("====================================")
# check whether we're in CI, in that case we make the run a bit cheaper
ci = "CI" in os.environ and os.environ['CI'].lower() in ['1', 'true']
nparticles = 3 if ci else 10
degree = 2 if ci else 3

"""
This examples demonstrate how to use SIMSOPT to compute guiding center
trajectories of particles
"""
for c in base_curves:
    c.x=c.x*1.7

bs = BiotSavart(coils)
bs.set_points(s_inner.gamma().reshape(-1,3))
Bfield=bs.B()
modB = np.linalg.norm(Bfield, axis=-1)
avgB = np.mean(modB)
for curr in base_currents:
    curr.x=curr.x*5.9/avgB


bs = BiotSavart(coils)
bs.set_points(s_inner.gamma().reshape(-1,3))
Bfield=bs.B()
modB = np.linalg.norm(Bfield, axis=-1)
avgB = np.mean(modB)

print("Mean(|B|) on surface close to axis =", avgB)
print("Mean(surface close to axis radius) =", np.mean(np.linalg.norm(s_inner.gamma(), axis=-1)))

sc_particle = SurfaceClassifier(s_outer, h=0.1, p=2)
n = 32
rs = np.linalg.norm(s_outer.gamma()[:, :, 0:2], axis=2)
zs = s_outer.gamma()[:, :, 2]

nfp=2
rrange = (np.min(rs), np.max(rs), n)
phirange = (0, 2*np.pi/2, n*2)
zrange = (0, np.max(zs), n//2)
bsh = InterpolatedField(
    bs, degree, rrange, phirange, zrange, True, nfp=2, stellsym=True
)


def trace_particles(bfield, label, mode='gc_vac'):
    t1 = time.time()
    phis = [(i/4)*(2*np.pi/nfp) for i in range(4)]
    gc_tys, gc_phi_hits = trace_particles_starting_on_surface(
        s_inner, bfield, nparticles, tmax=1e-3, seed=1, mass=ALPHA_PARTICLE_MASS, charge=ALPHA_PARTICLE_CHARGE,
        Ekin=3.5e6*ONE_EV, umin=-1, umax=+1, comm=comm,
        phis=phis, tol=1e-10,
        stopping_criteria=[LevelsetStoppingCriterion(sc_particle.dist)], mode=mode,
        forget_exact_path=True)
    t2 = time.time()
    print(f"Time for particle tracing={t2-t1:.3f}s. Num steps={sum([len(l) for l in gc_tys])//nparticles}", flush=True)
    if comm is None or comm.rank == 0:
        particles_to_vtk(gc_tys, OUT_DIR + f'particles_{label}_{mode}')
        plot_poincare_data(gc_phi_hits, phis, OUT_DIR + f'poincare_particle_{label}_loss.png', mark_lost=True)
        plot_poincare_data(gc_phi_hits, phis, OUT_DIR + f'poincare_particle_{label}.png', mark_lost=False)


print('Error in B', bsh.estimate_error_B(1000), flush=True)
print('Error in AbsB', bsh.estimate_error_GradAbsB(1000), flush=True)
trace_particles(bsh, 'bsh', 'gc_vac')
# trace_particles(bsh, 'bsh', 'full')
# trace_particles(bs, 'bs', 'gc')

print("End of 1_Simple/tracing_particle.py")
print("====================================")
