### Crossing arrow and secondary-button edits

1. In **Open last folder**, click **OK**.
2. In **Choose annotation classes**, choose **Defaults**.
3. In **Use model.conf?**, click **Yes**; wait for image 1 of 9 to load fully.
4. Enter `2` in the image-number field and press Return; wait for the empty second image.
5. Click the canvas, then press `Q`.
6. Draw a large four-sided free polygon centrally, with clear canvas on its left and right. Click its first vertex to close it.
7. Click inside the polygon. Confirm four vertices and note where vertex label 1 is displayed.
8. Click empty canvas to deselect it, then press `A`.
9. Click in empty space left of the polygon to set the arrow base.
10. Click in empty space right of the polygon so the arrow crosses it completely; wait for redraw.
11. Select the polygon. Confirm exactly four vertices and that vertex label 1 remains at its original vertex; then deselect it.
12. Click the arrow shaft to select it.
13. With the secondary/right mouse button, drag one arrow endpoint visibly while keeping the arrow crossing the polygon. Confirm that it moves and no context menu remains open.
14. Select the polygon. Confirm again that it has four vertices and the same vertex 1.
15. With the secondary/right mouse button, drag one visible polygon vertex. Confirm that this vertex moves and no context menu remains open.
16. Click **Save** and wait for completion.
17. Close using the macOS window close button. Report any prompt or deviation.

Required result: the arrow and endpoint edit persist; neither arrow action changes polygon count, coordinates, or order; only the explicit polygon drag changes its targeted vertex; and both secondary-button Tk routes replay without a lingering menu.
