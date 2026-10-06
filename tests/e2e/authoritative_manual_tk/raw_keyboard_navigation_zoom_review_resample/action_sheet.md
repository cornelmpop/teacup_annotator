### Raw keyboard navigation, zoom, review, and resampling

1. In **Open last folder**, click **OK**.
2. In **Choose annotation classes**, choose **Defaults**.
3. In **Use model.conf?**, click **Yes**; wait for image 1 of 9 to load fully.
4. Enter `2` in the image-number field and press Return; wait for image 2.
5. Click empty canvas to give it focus.
6. Press Left Arrow; confirm image 1 appears.
7. Press Right Arrow; confirm image 2 appears.
8. Press Left Arrow again; confirm image 1 appears.
9. Press numeric-keypad `+` three times, waiting for each zoom increase.
10. Press numeric-keypad `-` three times, waiting for each zoom decrease.
11. Select a detailed free-polygon annotation, not a rectangle.
12. Press `S`; confirm that its outline is resampled.
13. Press `F`; confirm that the current image's review-flag state changes.
14. Click **Save** and wait for completion.
15. Close using the macOS window close button. Report any prompt or deviation.

Required result: navigation proceeds 2→1→2→1; all six keypad inputs change zoom; `S` resamples the selected polygon; and `F` toggles the review flag. Resampled geometry and review state must persist after Save and replay.
