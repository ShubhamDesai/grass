"""Test functions in grass.script.setup"""

import multiprocessing
import os
import sys
from functools import partial

import pytest

import grass.script as gs
from grass.app.data import MapsetLockingException

RUNTIME_GISBASE_SHOULD_BE_PRESENT = "Runtime (GISBASE) should be present"
SESSION_FILE_NOT_DELETED = "Session file not deleted"

xfail_mp_spawn = pytest.mark.xfail(
    multiprocessing.get_start_method() == "spawn",
    reason="Multiprocessing using 'spawn' start method requires pickable functions",
    raises=AttributeError,
    strict=True,
)


# This is useful when we want to ensure that function like init does
# not change the global environment.
def run_in_subprocess(function):
    """Run function in a separate process

    The function must take a Queue and put its result there.
    The result is then returned from this function.
    """
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=function, args=(queue,))
    process.start()
    result = queue.get()
    process.join()
    return result


def test_init_as_context_manager(tmp_path):
    """Check that init function return value works as a context manager"""
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy()) as session:
        gs.run_command("g.region", flags="p", env=session.env)
        session_file = session.env["GISRC"]
        assert os.path.exists(session_file)
    assert not os.path.exists(session_file)


def test_init_session_finish(tmp_path):
    """Check that init works with finish on the returned session object"""
    project = tmp_path / "test"
    gs.create_project(project)
    session = gs.setup.init(project, env=os.environ.copy())
    gs.run_command("g.region", flags="p", env=session.env)
    session_file = session.env["GISRC"]
    session.finish()
    with pytest.raises(ValueError):  # noqa: PT011
        session.finish()
    assert not session.active
    assert not os.path.exists(session_file)


def test_init_finish_global_functions_with_env(tmp_path):
    """Check that init and finish global functions work"""
    project = tmp_path / "test"
    gs.create_project(project)
    env = os.environ.copy()
    gs.setup.init(project, env=env)
    gs.run_command("g.region", flags="p", env=env)
    session_file = env["GISRC"]
    gs.setup.finish(env=env)

    assert not os.path.exists(session_file)


def init_finish_global_functions_capture_strerr0_partial(tmp_path, queue):
    gs.set_capture_stderr(True)
    project = tmp_path / "test"
    gs.create_project(project)
    gs.setup.init(project)
    gs.run_command("g.region", flags="p")
    runtime_present = bool(os.environ.get("GISBASE"))
    queue.put((os.environ["GISRC"], runtime_present))
    gs.setup.finish()


def test_init_finish_global_functions_capture_strerr0_partial(tmp_path):
    """Check that init and finish global functions work with global env using a partial
    function
    """

    init_finish = partial(
        init_finish_global_functions_capture_strerr0_partial, tmp_path
    )
    session_file, runtime_present = run_in_subprocess(init_finish)
    assert session_file, "Expected file name from the subprocess"
    assert runtime_present, RUNTIME_GISBASE_SHOULD_BE_PRESENT
    assert not os.path.exists(session_file), SESSION_FILE_NOT_DELETED


@xfail_mp_spawn
def test_init_finish_global_functions_capture_strerr0(tmp_path):
    """Check that init and finish global functions work with global env"""

    def init_finish(queue):
        gs.set_capture_stderr(True)
        project = tmp_path / "test"
        gs.create_project(project)
        gs.setup.init(project)
        gs.run_command("g.region", flags="p")
        runtime_present = bool(os.environ.get("GISBASE"))
        queue.put((os.environ["GISRC"], runtime_present))
        gs.setup.finish()

    session_file, runtime_present = run_in_subprocess(init_finish)
    assert session_file, "Expected file name from the subprocess"
    assert runtime_present, RUNTIME_GISBASE_SHOULD_BE_PRESENT
    assert not os.path.exists(session_file), SESSION_FILE_NOT_DELETED


@xfail_mp_spawn
def test_init_finish_global_functions_capture_strerrX(tmp_path):
    """Check that init and finish global functions work with global env"""

    def init_finish(queue):
        gs.set_capture_stderr(True)
        project = tmp_path / "test"
        gs.create_project(project)
        gs.setup.init(project)
        gs.run_command("g.region", flags="p")
        runtime_present = bool(os.environ.get("GISBASE"))
        session_file = os.environ["GISRC"]
        gs.setup.finish()
        runtime_present_after = bool(os.environ.get("GISBASE"))
        queue.put((session_file, runtime_present, runtime_present_after))

    session_file, runtime_present, runtime_present_after = run_in_subprocess(
        init_finish
    )
    assert session_file, "Expected file name from the subprocess"
    assert runtime_present, RUNTIME_GISBASE_SHOULD_BE_PRESENT
    assert not os.path.exists(session_file), SESSION_FILE_NOT_DELETED
    # This is testing the current implementation behavior, but it is not required
    # to be this way in terms of design.
    assert runtime_present_after, "Runtime should continue to be present"


@xfail_mp_spawn
def test_init_finish_global_functions_isolated(tmp_path):
    """Check that init and finish global functions work with global env"""

    def init_finish(queue):
        gs.set_capture_stderr(True)
        project = tmp_path / "test"
        gs.create_project(project)
        gs.setup.init(project)
        gs.run_command("g.region", flags="p")
        runtime_present_during = bool(os.environ.get("GISBASE"))
        session_file_variable_present_during = bool(os.environ.get("GISRC"))
        session_file = os.environ.get("GISRC")
        if session_file:
            session_file_present_during = os.path.exists(session_file)
        else:
            session_file_present_during = False
        gs.setup.finish()
        session_file_variable_present_after = bool(os.environ.get("GISRC"))
        runtime_present_after = bool(os.environ.get("GISBASE"))
        queue.put(
            (
                session_file,
                session_file_variable_present_during,
                session_file_present_during,
                session_file_variable_present_after,
                runtime_present_during,
                runtime_present_after,
            )
        )

    (
        session_file,
        session_file_variable_present_during,
        session_file_present_during,
        session_file_variable_present_after,
        runtime_present_during,
        runtime_present_after,
    ) = run_in_subprocess(init_finish)

    # Runtime
    assert runtime_present_during, RUNTIME_GISBASE_SHOULD_BE_PRESENT
    # This is testing the current implementation behavior, but it is not required
    # to be this way in terms of design.
    assert runtime_present_after, "Expected GISBASE to be present when finished"

    # Session
    assert session_file_present_during, "Expected session file to be present"
    assert session_file_variable_present_during, "Variable GISRC should be present"
    assert not session_file_variable_present_after, "Not expecting GISRC when finished"
    assert not os.path.exists(session_file), SESSION_FILE_NOT_DELETED


@xfail_mp_spawn
@pytest.mark.usefixtures("mock_no_session")
def test_init_as_context_manager_env_attribute(tmp_path):
    """Check that session has global environment as attribute"""

    def workload(queue):
        project = tmp_path / "test"
        gs.create_project(project)
        with gs.setup.init(project) as session:
            gs.run_command("g.region", flags="p", env=session.env)
            session_file = os.environ["GISRC"]
            runtime_present = bool(os.environ.get("GISBASE"))
            queue.put((session_file, os.path.exists(session_file), runtime_present))

    session_file, file_existed, runtime_present = run_in_subprocess(workload)
    assert session_file, "Expected file name from the subprocess"
    assert file_existed, "File should have been present"
    assert runtime_present, RUNTIME_GISBASE_SHOULD_BE_PRESENT
    assert not os.path.exists(session_file), SESSION_FILE_NOT_DELETED
    assert not os.environ.get("GISRC")
    assert not os.environ.get("GISBASE")


@pytest.mark.usefixtures("mock_no_session")
def test_init_environment_isolation(tmp_path):
    """Check that only the provided environment is modified"""
    project = tmp_path / "test"
    gs.create_project(project)
    env = os.environ.copy()
    with gs.setup.init(project, env=env) as session:
        gs.run_command("g.region", flags="p", env=session.env)
        assert env.get("GISBASE")
        assert env.get("GISRC")
        # Check that the global environment is intact.
        assert not os.environ.get("GISRC")
        assert not os.environ.get("GISBASE")
    assert not env.get("GISRC")
    # We test if the global environment is intact after closing the session.
    assert not os.environ.get("GISRC")
    assert not os.environ.get("GISBASE")


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Locking is disabled on Windows"
)
def test_init_lock_global_environment(tmp_path):
    """Check that init function can lock a mapset and respect that lock.

    Locking should fail regardless of using the same environment or not.
    Here we are using a global environment as if these would be independent processes.
    """
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy(), lock=True) as top_session:
        gs.run_command("g.region", flags="p", env=top_session.env)
        # An attempt to lock a locked mapset should fail.
        with (
            pytest.raises(MapsetLockingException, match=r"Concurrent.*mapset"),
            gs.setup.init(project, env=os.environ.copy(), lock=True),
        ):
            pass


def test_init_ignore_lock_global_environment(tmp_path):
    """Check that no locking ignores the present lock"""
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy(), lock=True) as top_session:
        gs.run_command("g.region", flags="p", env=top_session.env)
        with gs.setup.init(
            project, env=os.environ.copy(), lock=False
        ) as nested_session:
            gs.run_command("g.region", flags="p", env=nested_session.env)
        # No locking is the default.
        with gs.setup.init(project, env=os.environ.copy()) as nested_session:
            gs.run_command("g.region", flags="p", env=nested_session.env)


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Locking is disabled on Windows"
)
def test_init_lock_nested_environments(tmp_path):
    """Check that init function can lock a mapset using nested environments"""
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy(), lock=True) as top_session:
        gs.run_command("g.region", flags="p", env=top_session.env)
        # An attempt to lock a locked mapset should fail.
        with (
            pytest.raises(MapsetLockingException, match=r"Concurrent.*mapset"),
            gs.setup.init(project, env=top_session.env.copy(), lock=True),
        ):
            pass


def test_init_ignore_lock_nested_environments(tmp_path):
    """Check that No locking ignores the present lock using nested environments"""
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy(), lock=True) as top_session:
        gs.run_command("g.region", flags="p", env=top_session.env)
        with gs.setup.init(
            project, env=top_session.env.copy(), lock=False
        ) as nested_session:
            gs.run_command("g.region", flags="p", env=nested_session.env)
        # No locking is the default.
        with gs.setup.init(project, env=top_session.env.copy()) as nested_session:
            gs.run_command("g.region", flags="p", env=nested_session.env)


def test_init_force_unlock(tmp_path):
    """Force-unlocking should remove an existing lock"""
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy(), lock=True) as top_session:
        gs.run_command("g.region", flags="p", env=top_session.env)
        with gs.setup.init(
            project, env=os.environ.copy(), lock=True, force_unlock=True
        ) as nested_session:
            gs.run_command("g.region", flags="p", env=nested_session.env)


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Locking is disabled on Windows"
)
def test_init_lock_fail_with_unlock_false(tmp_path):
    """No force-unlocking should fail if there is an existing lock"""
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy(), lock=True) as top_session:
        gs.run_command("g.region", flags="p", env=top_session.env)
        with (
            pytest.raises(MapsetLockingException, match=r"Concurrent.*mapset"),
            gs.setup.init(
                project, env=os.environ.copy(), lock=True, force_unlock=False
            ),
        ):
            pass


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Locking is disabled on Windows"
)
def test_init_lock_fail_without_unlock(tmp_path):
    """No force-unlocking is the default and it should fail with an existing lock"""
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy(), lock=True) as top_session:
        gs.run_command("g.region", flags="p", env=top_session.env)
        with (
            pytest.raises(MapsetLockingException, match=r"Concurrent.*mapset"),
            gs.setup.init(project, env=os.environ.copy(), lock=True),
        ):
            pass


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Locking is disabled on Windows"
)
def test_init_lock_timeout_fail(tmp_path):
    """Fail with locked mapset with non-zero timeout"""
    project = tmp_path / "test"
    gs.create_project(project)
    with gs.setup.init(project, env=os.environ.copy(), lock=True) as top_session:
        gs.run_command("g.region", flags="p", env=top_session.env)
        with (
            pytest.raises(MapsetLockingException, match=r"Concurrent.*mapset"),
            gs.setup.init(project, env=os.environ.copy(), lock=True, timeout=2),
        ):
            pass
