package io.github.quezka.quire.ui

import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.material3.TextFieldColors
import androidx.compose.material3.OutlinedTextField as MaterialOutlinedTextField

/**
 * The app's text box: Material's, except that pressing Enter (or Done on the keyboard) in a
 * single-line box lets go of focus and the keyboard, as in the desktop apps. Boxes that set
 * their own keyboard action keep it. Every screen in this package uses this one, not Material's.
 */
@Composable
fun OutlinedTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    readOnly: Boolean = false,
    textStyle: TextStyle = LocalTextStyle.current,
    label: @Composable (() -> Unit)? = null,
    placeholder: @Composable (() -> Unit)? = null,
    leadingIcon: @Composable (() -> Unit)? = null,
    trailingIcon: @Composable (() -> Unit)? = null,
    supportingText: @Composable (() -> Unit)? = null,
    isError: Boolean = false,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
    singleLine: Boolean = false,
    maxLines: Int = if (singleLine) 1 else Int.MAX_VALUE,
    minLines: Int = 1,
    shape: Shape = OutlinedTextFieldDefaults.shape,
    colors: TextFieldColors = OutlinedTextFieldDefaults.colors(),
) {
    val focus = LocalFocusManager.current
    val leave = singleLine && keyboardActions == KeyboardActions.Default
    MaterialOutlinedTextField(
        value, onValueChange,
        modifier.then(if (leave) Modifier.onPreviewKeyEvent { e ->
            if (e.type == KeyEventType.KeyDown && (e.key == Key.Enter || e.key == Key.NumPadEnter)) {
                focus.clearFocus(); true
            } else false
        } else Modifier),
        enabled, readOnly, textStyle, label, placeholder, leadingIcon, trailingIcon,
        supportingText = supportingText, isError = isError, visualTransformation = visualTransformation,
        keyboardOptions = keyboardOptions,
        keyboardActions = if (leave) KeyboardActions(
            onDone = { focus.clearFocus() }, onGo = { focus.clearFocus() },
            onSearch = { focus.clearFocus() }, onSend = { focus.clearFocus() }) else keyboardActions,
        singleLine = singleLine, maxLines = maxLines, minLines = minLines, shape = shape, colors = colors,
    )
}
