import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Arrays;
import org.gradle.api.Project;
import org.gradle.testfixtures.ProjectBuilder;
import org.gradle.testfixtures.internal.ProjectBuilderImpl;

/** Fixed caller for the unchanged Runtime app-server package task. Authority belongs to its caller. */
public final class RuntimePackageMain {
    private static Path absolute(String value) {
        Path path = Path.of(value);
        if (!path.isAbsolute() || !path.equals(path.normalize()))
            throw new IllegalArgumentException("Runtime package paths must be absolute and normalized");
        return path;
    }
    private static void require(boolean value, String message) {
        if (!value) throw new IllegalArgumentException(message);
    }
    private static void basename(String value) {
        require(!value.isEmpty() && !value.equals(".") && !value.equals("..") &&
            !value.contains("/") && !value.contains("\\"), "Runtime package names must be basenames");
    }
    public static void main(String[] args) throws Exception {
        require(args.length == 17, "Expected fixed Runtime package arguments: privateRoot archive supervisor license notice output releaseTag libraryVersion appServerVersion target classifier asset archiveSha256 archiveEntry binarySha256 executableName supervisorExecutableName");
        require(Arrays.stream(args).noneMatch(String::isBlank), "Runtime package arguments must be nonempty");
        require(ZoneId.systemDefault().normalized().equals(ZoneOffset.UTC), "Runtime package requires the fixed UTC timezone");
        Path root = absolute(args[0]);
        require(!Files.exists(root, LinkOption.NOFOLLOW_LINKS), "Runtime package private root must be fresh");
        require(root.getParent().equals(root.getParent().toRealPath()), "Runtime package private parent must be canonical");
        Path home = root.resolve("home"), temporary = root.resolve("tmp");
        require(home.toString().equals(System.getProperty("user.home")) &&
            home.toString().equals(System.getenv("GRADLE_USER_HOME")) &&
            home.toString().equals(System.getenv("HOME")), "Runtime package requires private JVM and Gradle user homes");
        require(temporary.toString().equals(System.getProperty("java.io.tmpdir")), "Runtime package requires private JVM temporary directory");
        for (String variable : new String[]{"JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "JAVA_OPTS", "GRADLE_OPTS"})
            require(System.getenv(variable) == null || System.getenv(variable).isEmpty(), "Runtime package rejects external JVM options");
        for (int index : new int[]{1, 2, 3, 4}) {
            Path input = absolute(args[index]);
            require(Files.isRegularFile(input, LinkOption.NOFOLLOW_LINKS) && input.equals(input.toRealPath()) &&
                !input.startsWith(root), "Runtime package requires regular canonical caller-owned inputs");
        }
        Path output = absolute(args[5]);
        require(!output.startsWith(root) && !Files.exists(output, LinkOption.NOFOLLOW_LINKS) &&
            output.getParent().equals(output.getParent().toRealPath()), "Runtime package output must be fresh outside bootstrap scratch");
        require(args[12].matches("[0-9a-f]{64}") && args[14].matches("[0-9a-f]{64}"), "Runtime package requires exact archive and executable digests");
        for (int index : new int[]{11, 13, 15, 16}) basename(args[index]);
        Files.createDirectory(root);
        try {
            Files.createDirectory(home);
            Files.createDirectory(temporary);
            Files.createDirectory(root.resolve("project"));
            Worker.run(args, root);
        } finally {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override public FileVisitResult visitFile(Path path, BasicFileAttributes attributes) throws IOException {
                    Files.delete(path); return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult postVisitDirectory(Path path, IOException error) throws IOException {
                    if (error != null) throw error;
                    Files.delete(path); return FileVisitResult.CONTINUE;
                }
            });
        }
    }
    /** Loaded only after JDK-only private-scope checks; no settings or task graph is evaluated. */
    private static final class Worker {
        static void run(String[] a, Path root) {
            Project project = ProjectBuilder.builder().withProjectDir(root.resolve("project").toFile())
                .withGradleUserHomeDir(root.resolve("home").toFile()).build();
            try {
                project.getGradle().getStartParameter().setOffline(true);
                PackageDesktopCodexRuntimeTask task = project.getTasks().create("packageRuntime", PackageDesktopCodexRuntimeTask.class);
                task.getOfflineMode().set(true);
                task.getLocalArchive().set(Path.of(a[1]).toFile());
                task.getSupervisorExecutable().set(Path.of(a[2]).toFile());
                task.getLicenseFile().set(Path.of(a[3]).toFile());
                task.getNoticeFile().set(Path.of(a[4]).toFile());
                task.getOutputFile().set(Path.of(a[5]).toFile());
                task.getReleaseTag().set(a[6]);
                task.getLibraryVersion().set(a[7]);
                task.getAppServerVersion().set(a[8]);
                task.getTarget().set(a[9]);
                task.getClassifier().set(a[10]);
                task.getAsset().set(a[11]);
                task.getArchiveSha256().set(a[12]);
                task.getArchiveEntry().set(a[13]);
                task.getBinarySha256().set(a[14]);
                task.getExecutableName().set(a[15]);
                task.getSupervisorExecutableName().set(a[16]);
                task.packageRuntime();
            } finally { ProjectBuilderImpl.stop(project); }
        }
    }
}
