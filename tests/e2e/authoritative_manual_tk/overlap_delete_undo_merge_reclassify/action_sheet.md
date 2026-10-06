### Recording 8B — Overlap deletion, Undo, merge, and reclassification

1. In **Open last folder**, click **OK**.
2. In **Choose annotation classes**, choose **Use annotation/default classes**.
3. In **Use model.conf?**, click **Yes**; wait until 9 images load.
4. Use the image-index field to enter `2`, then press Return. Wait for `2 / 9`; this image should have no annotations.
5. In the central area of the image, press `R`.
6. Left-drag a large rectangle from approximately the upper-left of the central area to its lower-right. Release and wait until `lithics (1)` appears in the Classes panel.
7. Press `R` again.
8. Draw a smaller rectangle whose upper-left portion overlaps the large rectangle’s lower-right portion, but whose lower-right portion extends beyond the large rectangle. Wait for `lithics (2)`.
9. Control-click inside the area where both rectangles overlap.
10. Open the **Delete** submenu. It should contain two `lithics (… px)` entries. Choose the lower entry, representing the smaller rectangle.
11. Wait until the smaller rectangle disappears and the Classes panel shows `lithics (1)`.
12. Control-click empty image space outside both rectangles and choose **Undo last action**. Wait until both rectangles return and the panel shows `lithics (2)`.
13. Control-click inside the large rectangle’s upper-left-only area and choose **Merge**.
14. Click inside the smaller rectangle’s lower-right-only area. Wait until the two rectangles become one enclosing rectangle and the panel shows `lithics (1)`.
15. Control-click inside the merged rectangle, open **Change class**, and choose `figure_caption`.
16. Confirm the Classes panel shows `figure_caption (1)` and `lithics (0)`.
17. Click **Save** and wait for completion.
18. Close the main window using the macOS red button. No prompt is expected; if one appears, stop.

After closing, reply with `no deviations` or list every deviation.
