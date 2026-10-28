import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Properties;

/** A later SQL error distinguishes lazy prefix reads from full materialization. */
public class TestJdbcStreaming {
    private static final String QUERY =
        "SELECT CASE WHEN i >= 1000000 THEN error('past-prefix') ELSE i END " +
        "FROM range(10000000) r(i)";

    private static void readPrefix(String url, Properties properties) throws Exception {
        try (Connection connection = DriverManager.getConnection(url, properties);
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(QUERY)) {
            for (int i = 0; i < 10; i++) {
                if (!result.next() || result.getLong(1) != i) {
                    throw new AssertionError("Missing or unexpected prefix row " + i);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Properties endpoint = new Properties();
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            endpoint.load(input);
        }
        Properties driver = new Properties();
        endpoint.stringPropertyNames().stream()
            .filter(key -> key.startsWith("jdbc.property."))
            .forEach(key -> driver.setProperty(key.substring("jdbc.property.".length()),
                                              endpoint.getProperty(key)));
        // A single thread makes the late-error prefix check deterministic.
        driver.setProperty("threads", "1");
        driver.setProperty("memory_limit", "64MB");
        driver.setProperty("max_temp_directory_size", "0B");
        driver.setProperty("temp_directory", args[1] + ".tmp");
        String url = "jdbc:duckdb:" + args[1];
        // Create a fixture file before using the endpoint's read-only connection.
        try (Connection ignored = DriverManager.getConnection(url)) { }
        readPrefix(url, driver);
        System.out.println("Configured driver returned ten rows before the later SQL error");

        // The negative control must evaluate the later error before yielding rows.
        Properties materialized = (Properties) driver.clone();
        materialized.remove("jdbc_stream_results");
        try {
            readPrefix(url, materialized);
            throw new AssertionError("Expected materialization to encounter the later error");
        } catch (SQLException expected) {
            if (!expected.getMessage().contains("past-prefix")) {
                throw expected;
            }
        }
        System.out.println("Default materialization encountered the later SQL error");

        // Streaming must also work with a multi-thread configuration and aggregation.
        driver.setProperty("threads", "4");
        try (Connection connection = DriverManager.getConnection(url, driver);
             Statement statement = connection.createStatement()) {
            try (ResultSet result = statement.executeQuery("SELECT current_setting('threads')")) {
                if (!result.next() || result.getInt(1) != 4) {
                    throw new AssertionError("Streaming changed the configured thread count");
                }
            }
            try (ResultSet result = statement.executeQuery(
                     "SELECT sum(i) FROM range(1000000) r(i)")) {
                if (!result.next() || result.getLong(1) != 499999500000L || result.next()) {
                    throw new AssertionError("Incorrect full-input aggregation result");
                }
            }
        }
        System.out.println("Streaming retained four configured threads and complete aggregation");
    }
}
