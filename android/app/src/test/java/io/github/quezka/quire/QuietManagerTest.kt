package io.github.quezka.quire

import android.app.Application
import android.app.NotificationManager
import androidx.test.core.app.ApplicationProvider
import io.github.quezka.quire.data.MemoryRowStore
import io.github.quezka.quire.data.Records
import io.github.quezka.quire.data.Repository
import io.github.quezka.quire.domain.Event
import io.github.quezka.quire.domain.QuietSettings
import io.github.quezka.quire.notify.Notifier
import io.github.quezka.quire.notify.QuietManager
import io.github.quezka.quire.sync.MemorySettings
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import java.time.LocalDate
import java.time.LocalDateTime

/** Do Not Disturb has to come off when the event ends, whatever the phone reports by then. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], application = Application::class)
class QuietManagerTest {
    private val context: Application = ApplicationProvider.getApplicationContext()
    private val day = LocalDate.of(2026, 11, 4)
    private val settings = MemorySettings()
    private var now = day.atTime(9, 30)
    private lateinit var quiet: QuietManager
    private val system get() = context.getSystemService(NotificationManager::class.java)

    @Before fun setUp() {
        shadowOf(system).setNotificationPolicyAccessGranted(true)
        system.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_ALL)
        val repo = Repository(Records(MemoryRowStore()), today = { day })
        repo.saveEvent(Event("e", day, 9 * 60, 11 * 60, "Exam", "", "#000000"))
        quiet = QuietManager(context, repo, settings, Notifier(context)) { now }
        QuietSettings(enabled = true).save(settings)
    }

    private fun at(hour: Int): LocalDateTime = day.atTime(hour, 0)

    @Test fun itGoesOnAndComesOffAtTheEnd() {
        quiet.update()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALARMS, system.currentInterruptionFilter)
        now = at(11)
        quiet.update()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, system.currentInterruptionFilter)
        assertNull(settings.get("quiet.applied"))
    }

    @Test fun itComesOffEvenIfThePhoneReportsAnotherSilenceByThen() {
        quiet.update()
        system.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_PRIORITY)  // this used to stay on for good
        now = at(11)
        quiet.update()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, system.currentInterruptionFilter)
    }

    @Test fun aSilenceLeftBehindIsNotTakenForTheWayThingsWere() {
        system.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_ALARMS)
        quiet.update()
        now = at(11)
        quiet.update()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, system.currentInterruptionFilter)
    }

    @Test fun losingTheAccessDoesntForgetItIsOurs() {
        quiet.update()
        shadowOf(system).setNotificationPolicyAccessGranted(false)
        now = at(11)
        quiet.update()
        assertEquals("1", settings.get("quiet.applied"))
        shadowOf(system).setNotificationPolicyAccessGranted(true)
        quiet.update()
        assertEquals(NotificationManager.INTERRUPTION_FILTER_ALL, system.currentInterruptionFilter)
    }
}
