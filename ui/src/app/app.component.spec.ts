import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { ReactiveFormsModule } from '@angular/forms';
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import { By } from '@angular/platform-browser';

import { MatToolbarModule } from '@angular/material/toolbar';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSnackBarModule } from '@angular/material/snack-bar';

import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { HarnessLoader } from '@angular/cdk/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { MatButtonHarness } from '@angular/material/button/testing';
import { MatSlideToggleHarness } from '@angular/material/slide-toggle/testing';
import { MatSnackBarHarness } from '@angular/material/snack-bar/testing';

import { AppComponent } from './app.component';
import { PvControl } from './pv-control.service';
import { HttpStatusInterceptor } from './http-status.service';


describe('AppComponent', () => {
  let loader: HarnessLoader;
  let httpMock: HttpTestingController;
  let component: AppComponent;
  let fixture: ComponentFixture<AppComponent>;
  let pvControlData: PvControl;
  let onePhaseSelector: MatSlideToggleHarness;
  let refreshButton: MatButtonHarness;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [
        BrowserAnimationsModule,
        HttpClientTestingModule,
        ReactiveFormsModule,
        MatToolbarModule,
        MatCardModule,
        MatFormFieldModule,
        MatInputModule,
        MatIconModule,
        MatButtonModule,
        MatSlideToggleModule,
        MatSnackBarModule,
      ],
      declarations: [
        AppComponent
      ],
      providers: [
        {
          provide: HTTP_INTERCEPTORS,
          useClass: HttpStatusInterceptor,
          multi: true,
        }
      ]
    }).compileComponents();

    fixture = TestBed.createComponent(AppComponent);
    loader = TestbedHarnessEnvironment.loader(fixture);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);

    pvControlData = {
      meter: {
        power_pv: 5000,
        power_consumption: 3000,
        power_grid: 2000
      },
      charger: {
        phases: 3,
        power_car: 2000,
        current_setpoint: 8
      }
    };

    onePhaseSelector = await loader.getHarness(MatSlideToggleHarness.with({selector: '#onePhaseSelector'}));
    refreshButton = await loader.getHarness(MatButtonHarness.with({selector: '#refresh'}));
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should render the app', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(component.onePhaseSelectorControl.value).toBe(false);
    expect(await onePhaseSelector.isChecked()).toBeFalse();
  });

  it('should refresh data', async () => {
    const refreshIcon = fixture.debugElement.query(By.css('#refresh mat-icon')).nativeElement;

    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);
    fixture.detectChanges();

    expect(refreshIcon.className).not.toContain('spin');
    expect(component.pvControl).toEqual(pvControlData);
    expect(component.onePhaseSelectorControl.value).toBe(false);

    pvControlData.charger.phases = 1;
    await refreshButton.click();

    expect(refreshIcon.className).toContain('spin');
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(component.onePhaseSelectorControl.value).toBe(true);
    expect(await onePhaseSelector.isChecked()).toBeTrue();
    expect(refreshIcon.className).not.toContain('spin');
  });

  it('should show an error msg on http problems', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    await refreshButton.click();
    httpMock.expectOne('./api/pvcontrol').flush('', {
      status: 500,
      statusText: 'Internal Server Error'
    });

    // snack bar is not below root element of fixture -> can't use loader
    const snackbar = await TestbedHarnessEnvironment.documentRootLoader(fixture).getHarness(MatSnackBarHarness);
    expect(await snackbar.getMessage()).toBe('HTTP 500 Internal Server Error - GET ./api/pvcontrol');
  });

  it('should allow to switch to one phase charging', async () => {
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    await onePhaseSelector.toggle();

    const req = httpMock.expectOne('./api/pvcontrol/charger/phases');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toBe(1);
    req.flush(null);

    pvControlData.charger.phases = 1;
    httpMock.expectOne('./api/pvcontrol').flush(pvControlData);

    expect(component.pvControl).toEqual(pvControlData);
    expect(component.onePhaseSelectorControl.value).toBe(true);
    expect(await onePhaseSelector.isChecked()).toBeTrue();
  });
});
